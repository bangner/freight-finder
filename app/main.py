"""ABC Freight shipper portal: FastAPI app.

Run with `python -m app` (see README). The LaunchDarkly SDK client is created
once at startup and closed at shutdown; every request reads flags from it.
"""

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path

import ldclient
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from ldclient import Config
from pydantic import BaseModel, Field

from app import assistant
from app.contexts import VISITORS, build_context, get_visitor
from app.features import HOS_RULES, PredictionServiceError, eta_predictions, hours_of_service, refresh_eta_predictions
from app.flags import ETA_FLAG, HOS_FLAG, FlagSubscription, evaluate_flags
from app.loads import as_dicts, loads_for
from app.settings import Settings, load_settings

log = logging.getLogger("abc_freight")

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
HEARTBEAT_SECONDS = 15
RECONNECT_MS = 2000
# Custom events the browser may send for Experimentation. Anything else is rejected.
ALLOWED_EVENTS = {"book-load-clicked"}


def build_state(visitor_key: str | None, settings: Settings) -> dict:
    """Everything the page shows for one visitor, gated by LaunchDarkly flags."""
    visitor = get_visitor(visitor_key)
    context = build_context(visitor)
    flags, reasons = evaluate_flags(context)
    loads = loads_for(visitor)

    state = {
        "visitor": {"key": visitor.key, "name": visitor.name, "org_name": visitor.org_name},
        "flags": flags,
        # Why LaunchDarkly served each value (TARGET_MATCH, RULE_MATCH, ...), shown in the footer.
        "reasons": reasons,
        "loads": as_dicts(loads),
        "eta": None,
        "hos": None,
        "assistant": assistant.status(visitor, context, loads, settings),
    }
    # New features only run when their flag says so.
    if flags[ETA_FLAG] is True:
        state["eta"] = eta_predictions(loads)
    if flags[HOS_FLAG] in HOS_RULES:
        state["hos"] = hours_of_service(loads, flags[HOS_FLAG])
    return state


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


async def state_events(visitor_key: str | None, settings: Settings):
    """SSE stream for one browser: a snapshot now, then a fresh one on every flag change."""
    context = build_context(get_visitor(visitor_key))
    subscription = FlagSubscription(context)
    try:
        yield f"retry: {RECONNECT_MS}\n\n"
        # Always start with the current state, so a new or reconnecting browser is correct
        # even if it missed changes while it was away.
        yield _sse("state", build_state(visitor_key, settings))
        while True:
            try:
                await asyncio.wait_for(subscription.queue.get(), timeout=HEARTBEAT_SECONDS)
            except TimeoutError:
                yield ": ping\n\n"  # keeps proxies from closing an idle connection
                continue
            # Several flags can change at once; send one combined update.
            while not subscription.queue.empty():
                subscription.queue.get_nowait()
            yield _sse("state", build_state(visitor_key, settings))
    finally:
        # Runs when the browser disconnects or the server stops.
        subscription.close()


class TrackRequest(BaseModel):
    visitor: str
    event: str


class AskRequest(BaseModel):
    visitor: str
    question: str = Field(min_length=1, max_length=500)


class FeedbackRequest(BaseModel):
    visitor: str
    feedback_token: str = Field(min_length=1, max_length=2000)
    positive: bool


def create_app(ld_config: Config | None = None, settings: Settings | None = None) -> FastAPI:
    """Build the app. Tests pass an ld_config backed by TestData; production passes nothing."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.settings = settings or load_settings()
        # Initialize the SDK once. set_config waits up to 5 s for the first flag data.
        ldclient.set_config(ld_config or Config(app.state.settings.sdk_key))
        if ldclient.get().is_initialized():
            log.info("LaunchDarkly SDK initialized")
        else:
            log.warning(
                "LaunchDarkly SDK not initialized yet; serving fallback values (all features off) "
                "and retrying in the background"
            )
        yield
        # Flushes pending analytics and experiment events, then closes the stream.
        ldclient.get().close()

    app = FastAPI(title="ABC Freight", lifespan=lifespan, docs_url=None, redoc_url=None)
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/healthz")
    def healthz():
        return {
            "status": "ok",
            "launchdarkly_initialized": ldclient.get().is_initialized(),
            "open_streams": FlagSubscription.open_count,
        }

    @app.get("/api/visitors")
    def visitors():
        return [
            {"key": v.key, "name": v.name, "role": v.role, "org_name": v.org_name, "plan": v.plan, "region": v.region}
            for v in VISITORS.values()
        ]

    @app.get("/api/state")
    def state(request: Request, visitor: str | None = None):
        return build_state(visitor, request.app.state.settings)

    @app.get("/events")
    async def events(request: Request, visitor: str | None = None):
        return StreamingResponse(
            state_events(visitor, request.app.state.settings),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.post("/api/eta/refresh")
    def refresh_eta(visitor: str | None = None):
        context = build_context(get_visitor(visitor))
        if ldclient.get().variation(ETA_FLAG, context, False) is not True:
            raise HTTPException(404, "ETA predictions are not enabled")
        try:
            refresh_eta_predictions()
        except PredictionServiceError as error:
            log.error("ETA refresh failed: %s", error)
            raise HTTPException(502, str(error)) from error

    @app.post("/api/track", status_code=202)
    def track(body: TrackRequest):
        if body.event not in ALLOWED_EVENTS:
            raise HTTPException(400, "Unknown event")
        ldclient.get().track(body.event, build_context(get_visitor(body.visitor)))
        return {"tracked": body.event}

    @app.post("/api/assistant")
    def ask(request: Request, body: AskRequest):
        visitor = get_visitor(body.visitor)
        try:
            return assistant.ask(
                visitor,
                build_context(visitor),
                loads_for(visitor),
                body.question,
                request.app.state.settings,
            )
        except assistant.AssistantUnavailable as error:
            raise HTTPException(503, str(error)) from error
        except assistant.AssistantNoAnswer as error:
            # Cut off or declined: say so, rather than showing half an answer.
            raise HTTPException(502, str(error)) from error
        except Exception as error:
            raise HTTPException(502, "The assistant could not answer right now") from error

    @app.post("/api/assistant/feedback", status_code=202)
    def feedback(body: FeedbackRequest):
        try:
            assistant.record_feedback(build_context(get_visitor(body.visitor)), body.feedback_token, body.positive)
        except ValueError as error:
            raise HTTPException(400, "Invalid feedback token") from error
        return {"recorded": True}

    return app


load_dotenv()
app = create_app()
