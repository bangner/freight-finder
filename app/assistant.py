"""Dispatcher assistant, driven by a LaunchDarkly AI Config.

The model, its parameters and the prompt all come from the `dispatcher-assistant`
AI Config, so they can change in LaunchDarkly without a deploy. This demo calls
Anthropic's Messages API with MODEL_API_KEY. Without that key, or with
ASSISTANT_DRY_RUN=true, it runs as a dry run: it shows what LaunchDarkly served
and calls no model, so it costs nothing.
"""

import logging
import time
from typing import NamedTuple

import ldclient
from ldai.client import LDAIClient
from ldai.models import AICompletionConfig, AICompletionConfigDefault
from ldai.tracker import FeedbackKind, TokenUsage
from ldclient import Context

from app.contexts import Visitor
from app.flags import ASSISTANT_CONFIG
from app.loads import Load
from app.settings import Settings

log = logging.getLogger(__name__)

# If LaunchDarkly is unreachable or the AI Config is missing, the assistant is
# disabled and its panel stays hidden. The rest of the page is unaffected.
_DISABLED = AICompletionConfigDefault(enabled=False)
_DEFAULT_MAX_TOKENS = 400

# Optional "effort" on the AI Config variation (a model or custom parameter).
# Lower effort means less thinking, so fewer output tokens and a smaller bill.
EFFORT_LEVELS = ("low", "medium", "high", "xhigh", "max")

_ai_client: LDAIClient | None = None
_ai_client_for = None


class AssistantUnavailable(RuntimeError):
    """The AI Config is disabled for this visitor, or its provider is not supported."""


class AssistantNoAnswer(RuntimeError):
    """The model ran but gave no usable answer: it was cut off, or it declined."""


class ModelReply(NamedTuple):
    text: str
    input_tokens: int
    output_tokens: int
    stop_reason: str | None  # "end_turn" normally, "max_tokens" if cut off, "refusal" if declined


def is_dry_run(settings: Settings) -> bool:
    return settings.assistant_dry_run or not settings.model_api_key


def _ai() -> LDAIClient:
    # One AI client per SDK client. Tests swap the SDK client, so rebuild if it changed.
    global _ai_client, _ai_client_for
    client = ldclient.get()
    if _ai_client is None or _ai_client_for is not client:
        _ai_client, _ai_client_for = LDAIClient(client), client
    return _ai_client


def _config(visitor: Visitor, context: Context, loads: list[Load]) -> AICompletionConfig:
    # These variables fill {{shipper_name}} and {{loads}} in the prompt stored in LaunchDarkly.
    summary = "\n".join(
        f"- {load.id}: {load.origin} to {load.destination}, {load.status}, "
        f"scheduled {load.scheduled_arrival}, driver {load.driver}"
        for load in loads
    )
    variables = {"shipper_name": visitor.org_name, "loads": summary}
    return _ai().completion_config(ASSISTANT_CONFIG, context, _DISABLED, variables)


def status(visitor: Visitor, context: Context, loads: list[Load], settings: Settings) -> dict:
    config = _config(visitor, context, loads)
    enabled = bool(config.enabled and config.model)
    return {"enabled": enabled, "model": config.model.name if enabled else None, "dry_run": is_dry_run(settings)}


def _effort(config: AICompletionConfig) -> str | None:
    effort = config.model.get_parameter("effort") or config.model.get_custom("effort")
    if effort is None:
        return None  # the model's own default
    if effort not in EFFORT_LEVELS:
        log.warning("Ignoring effort %r from %s; expected one of %s", effort, ASSISTANT_CONFIG, EFFORT_LEVELS)
        return None
    return effort


def _call_model(
    api_key: str, model: str, max_tokens: int, effort: str | None, system: str, messages: list[dict]
) -> ModelReply:
    """Call the model provider. Tests replace this function."""
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)
    kwargs = {"system": system} if system else {}
    if effort:
        kwargs["output_config"] = {"effort": effort}
    response = client.messages.create(model=model, max_tokens=max_tokens, messages=messages, **kwargs)
    # Keep only text blocks: the model's thinking blocks are not part of the answer.
    text = "".join(block.text for block in response.content if block.type == "text")
    return ModelReply(text, response.usage.input_tokens, response.usage.output_tokens, response.stop_reason)


def _no_answer(reply: ModelReply, max_tokens: int) -> str | None:
    """Why a reply cannot be shown, or None when it can."""
    if reply.stop_reason == "max_tokens":
        # Thinking counts toward max_tokens, so a low limit can cut an answer short.
        return (
            f"The answer was cut off at max_tokens {max_tokens}. Raise max_tokens in the {ASSISTANT_CONFIG} AI Config."
        )
    if reply.stop_reason == "refusal":
        return "The model declined to answer that question."
    if not reply.text.strip():
        return "The model returned an empty answer."
    return None


def ask(visitor: Visitor, context: Context, loads: list[Load], question: str, settings: Settings) -> dict:
    config = _config(visitor, context, loads)
    if not config.enabled or not config.model:
        raise AssistantUnavailable("The assistant is turned off for this visitor.")
    if config.provider and config.provider.name and config.provider.name.lower() != "anthropic":
        raise AssistantUnavailable(f"Provider '{config.provider.name}' is not supported by this demo.")

    messages = config.messages or []
    system = "\n\n".join(m.content for m in messages if m.role == "system")
    history = [{"role": m.role, "content": m.content} for m in messages if m.role != "system"]
    history.append({"role": "user", "content": question})
    max_tokens = int(config.model.get_parameter("max_tokens") or _DEFAULT_MAX_TOKENS)
    effort = _effort(config)

    if is_dry_run(settings):
        # No model call and nothing tracked: show what LaunchDarkly served, at no cost.
        answer = (
            f"Dry run: no model was called. LaunchDarkly served {config.model.name} "
            f"(max_tokens {max_tokens}, effort {effort or 'model default'}) with this prompt:\n\n{system}"
        )
        return {"answer": answer, "model": config.model.name, "feedback_token": None, "dry_run": True}

    # One tracker per run. It reports duration, tokens and success to the AI Config.
    tracker = config.create_tracker()
    started = time.monotonic()
    try:
        reply = _call_model(settings.model_api_key, config.model.name, max_tokens, effort, system, history)
    except Exception:
        tracker.track_duration(int((time.monotonic() - started) * 1000))
        tracker.track_error()
        log.exception("Model call failed for %s", ASSISTANT_CONFIG)
        raise
    tracker.track_duration(int((time.monotonic() - started) * 1000))
    tokens_in, tokens_out = reply.input_tokens, reply.output_tokens
    tracker.track_tokens(TokenUsage(total=tokens_in + tokens_out, input=tokens_in, output=tokens_out))
    problem = _no_answer(reply, max_tokens)
    if problem:
        # Counted as an error, so it shows on the AI Config's Monitoring tab instead of as half a sentence.
        tracker.track_error()
        log.warning("%s: %s (stop_reason %s)", ASSISTANT_CONFIG, problem, reply.stop_reason)
        raise AssistantNoAnswer(problem)
    tracker.track_success()
    # The resumption token lets /feedback attach thumbs up/down to this same run later.
    return {
        "answer": reply.text,
        "model": config.model.name,
        "feedback_token": tracker.resumption_token,
        "dry_run": False,
    }


def record_feedback(context: Context, feedback_token: str, positive: bool) -> None:
    result = _ai().create_tracker(feedback_token, context)
    if not result.is_success():
        raise ValueError(result.error)
    kind = FeedbackKind.Positive if positive else FeedbackKind.Negative
    result.value.track_feedback({"kind": kind})
