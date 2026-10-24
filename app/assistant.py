"""Dispatcher assistant, driven by a LaunchDarkly AI Config.

The model name and the prompt both come from the `dispatcher-assistant`
AI Config, so they can change in LaunchDarkly without a deploy. This demo
calls Anthropic's Messages API; set MODEL_API_KEY to an Anthropic API key.
"""

import logging
import time

import ldclient
from ldai.client import LDAIClient
from ldai.models import AICompletionConfig, AICompletionConfigDefault
from ldai.tracker import FeedbackKind, TokenUsage
from ldclient import Context

from app.contexts import Visitor
from app.flags import ASSISTANT_CONFIG
from app.loads import Load

log = logging.getLogger(__name__)

# If LaunchDarkly is unreachable or the AI Config is missing, the assistant is
# disabled and its panel stays hidden. The rest of the page is unaffected.
_DISABLED = AICompletionConfigDefault(enabled=False)
_DEFAULT_MAX_TOKENS = 400

_ai_client: LDAIClient | None = None
_ai_client_for = None


class AssistantUnavailable(RuntimeError):
    """The AI Config is disabled for this visitor, or no model key is configured."""


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


def status(visitor: Visitor, context: Context, loads: list[Load], model_api_key: str | None) -> dict:
    config = _config(visitor, context, loads)
    enabled = bool(config.enabled and config.model and model_api_key)
    return {"enabled": enabled, "model": config.model.name if enabled else None}


def _call_model(api_key: str, model: str, max_tokens: int, system: str, messages: list[dict]):
    """Call the model provider. Tests replace this function."""
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)
    kwargs = {"system": system} if system else {}
    response = client.messages.create(model=model, max_tokens=max_tokens, messages=messages, **kwargs)
    text = "".join(block.text for block in response.content if block.type == "text")
    return text, response.usage.input_tokens, response.usage.output_tokens


def ask(visitor: Visitor, context: Context, loads: list[Load], question: str, model_api_key: str | None) -> dict:
    config = _config(visitor, context, loads)
    if not config.enabled or not config.model:
        raise AssistantUnavailable("The assistant is turned off for this visitor.")
    if not model_api_key:
        raise AssistantUnavailable("MODEL_API_KEY is not set on the server.")
    if config.provider and config.provider.name and config.provider.name.lower() != "anthropic":
        raise AssistantUnavailable(f"Provider '{config.provider.name}' is not supported by this demo.")

    messages = config.messages or []
    system = "\n\n".join(m.content for m in messages if m.role == "system")
    history = [{"role": m.role, "content": m.content} for m in messages if m.role != "system"]
    history.append({"role": "user", "content": question})
    max_tokens = int(config.model.get_parameter("max_tokens") or _DEFAULT_MAX_TOKENS)

    # One tracker per run. It reports duration, tokens and success to the AI Config.
    tracker = config.create_tracker()
    started = time.monotonic()
    try:
        answer, tokens_in, tokens_out = _call_model(model_api_key, config.model.name, max_tokens, system, history)
    except Exception:
        tracker.track_duration(int((time.monotonic() - started) * 1000))
        tracker.track_error()
        log.exception("Model call failed for %s", ASSISTANT_CONFIG)
        raise
    tracker.track_duration(int((time.monotonic() - started) * 1000))
    tracker.track_tokens(TokenUsage(total=tokens_in + tokens_out, input=tokens_in, output=tokens_out))
    tracker.track_success()
    # The resumption token lets /feedback attach thumbs up/down to this same run later.
    return {"answer": answer, "model": config.model.name, "feedback_token": tracker.resumption_token}


def record_feedback(context: Context, feedback_token: str, positive: bool) -> None:
    result = _ai().create_tracker(feedback_token, context)
    if not result.is_success():
        raise ValueError(result.error)
    kind = FeedbackKind.Positive if positive else FeedbackKind.Negative
    result.value.track_feedback({"kind": kind})
