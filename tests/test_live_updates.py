"""The SDK-listener-to-SSE bridge: snapshot on connect, push on change, cleanup on disconnect."""

import asyncio
import json

from app.flags import FlagSubscription
from app.main import state_events
from app.settings import Settings
from tests.conftest import FAKE_SDK_KEY, eta, hos

SETTINGS = Settings(sdk_key=FAKE_SDK_KEY, model_api_key=None)


async def next_state(stream, timeout=2.0) -> dict:
    """Read SSE chunks until the next `state` event and return its data."""
    while True:
        chunk = await asyncio.wait_for(anext(stream), timeout)
        if chunk.startswith("event: state"):
            return json.loads(chunk.split("data: ", 1)[1])


async def test_stream_sends_snapshot_then_live_changes(ld):
    eta(ld, False)
    stream = state_events("guest", SETTINGS)
    try:
        assert (await asyncio.wait_for(anext(stream), 1)).startswith("retry: ")
        assert (await next_state(stream))["eta"] is None

        eta(ld, True)  # like turning the flag on in the dashboard
        assert (await next_state(stream))["eta"] is not None

        eta(ld, False)  # like the rollback trigger
        assert (await next_state(stream))["eta"] is None
    finally:
        await stream.aclose()


async def test_reconnect_gets_current_state(ld):
    eta(ld, True)
    stream = state_events("guest", SETTINGS)
    try:
        assert (await next_state(stream))["eta"] is not None
    finally:
        await stream.aclose()


async def test_targeting_change_reaches_only_affected_visitors(ld):
    hos(ld)
    dana, alex = state_events("dana", SETTINGS), state_events("alex", SETTINGS)
    try:
        await next_state(dana)
        await next_state(alex)

        hos(ld, rules=True)  # enterprise rules: Dana (enterprise, CA) changes, Alex (free) does not

        assert (await next_state(dana))["hos"]["ruleset"] == "canada"
        try:
            await next_state(alex, timeout=0.5)
            raise AssertionError("Alex's value did not change, so no update should be sent")
        except TimeoutError:
            pass
    finally:
        await dana.aclose()
        await alex.aclose()


async def test_disconnect_removes_listeners(ld):
    before = FlagSubscription.open_count
    stream = state_events("guest", SETTINGS)
    await next_state(stream)
    assert FlagSubscription.open_count == before + 1
    await stream.aclose()
    assert FlagSubscription.open_count == before

    # A change after disconnect must not fail or reach the closed stream.
    eta(ld, True)
    await asyncio.sleep(0.1)
