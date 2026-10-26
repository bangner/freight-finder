"""LaunchDarkly flag keys, evaluation, and the bridge from SDK listeners to asyncio.

LaunchDarkly is the only source of truth. This module never stores a flag
value of its own; it asks the SDK every time.
"""

import asyncio
import logging

import ldclient
from ldclient import Config, Context

from app import __version__

log = logging.getLogger(__name__)

# Flag keys. These must match the flags you create in LaunchDarkly
# (terraform/ creates them; docs/SETUP.md covers both ways). The fallback values below are what the
# SDK returns if a flag is missing or LaunchDarkly has never been reachable,
# so each one is the safe, original behavior.
# Lifecycle: a temporary release flag is removed once its feature is fully
# released (docs/RUNBOOK.md, "Retire a release flag"); long-lived flags stay.
ETA_FLAG = "eta-predictions"  # boolean, Part 1. Temporary release flag
HOS_FLAG = "driver-hours-of-service"  # string: "off" | "us" | "canada", Part 2. Long-lived
ASSISTANT_CONFIG = "dispatcher-assistant"  # AI Config, extra credit. Long-lived

FLAG_FALLBACKS: dict[str, object] = {ETA_FLAG: False, HOS_FLAG: "off"}

# Every key an open browser should react to. An AI Config is a flag under the
# hood, so the same change listener covers it.
WATCHED_KEYS = (ETA_FLAG, HOS_FLAG, ASSISTANT_CONFIG)

APPLICATION_ID = "abc-freight"


def sdk_config(sdk_key: str, application_id: str = APPLICATION_ID, **options) -> Config:
    """SDK configuration that names the application connecting to LaunchDarkly.

    The SDK sends the application id and version with every connection, so
    LaunchDarkly can tell this app apart from the scripts and show which version
    is evaluating flags. Ids may use letters, digits, ".", "-" and "_".
    """
    return Config(sdk_key, application={"id": application_id, "version": __version__}, **options)


def evaluate_flags(context: Context) -> tuple[dict[str, object], dict[str, str]]:
    """Each flag's value for this context, and LaunchDarkly's reason for it.

    variation_detail is variation plus the evaluation reason. It records the same
    analytics and experiment events, so each flag is still evaluated once.
    """
    client = ldclient.get()
    values, reasons = {}, {}
    for key, fallback in FLAG_FALLBACKS.items():
        detail = client.variation_detail(key, context, fallback)
        values[key] = detail.value
        reasons[key] = describe_reason(detail.reason)
    return values, reasons


def describe_reason(reason: dict | None) -> str:
    """An evaluation reason in a few words, such as "RULE_MATCH (rule 2, in experiment)"."""
    if not reason:
        return "unknown"
    kind = reason.get("kind", "unknown")
    notes = []
    if kind == "RULE_MATCH" and "ruleIndex" in reason:
        notes.append(f"rule {reason['ruleIndex'] + 1}")  # the SDK counts rules from 0, people from 1
    if kind == "PREREQUISITE_FAILED" and reason.get("prerequisiteKey"):
        notes.append(reason["prerequisiteKey"])
    if kind == "ERROR" and reason.get("errorKind"):
        notes.append(reason["errorKind"])  # FLAG_NOT_FOUND means the flag key is missing or misspelled
    if reason.get("inExperiment"):
        notes.append("in experiment")
    return f"{kind} ({', '.join(notes)})" if notes else kind


class FlagSubscription:
    """Value-change listeners for one context, delivered onto an asyncio queue.

    The SDK calls listeners on its own worker thread, so each callback hands
    the event to the event loop with call_soon_threadsafe. Always call close()
    (the SSE endpoint does it in a finally block) or the listeners leak.
    """

    def __init__(self, context: Context, keys=WATCHED_KEYS):
        self.queue: asyncio.Queue[str] = asyncio.Queue()
        self._loop = asyncio.get_running_loop()
        self._tracker = ldclient.get().flag_tracker
        # add_flag_value_change_listener returns a handle; that handle, not our
        # callback, is what remove_listener needs.
        self._handles = [self._tracker.add_flag_value_change_listener(key, context, self._on_change) for key in keys]
        FlagSubscription.open_count += 1

    def _on_change(self, change) -> None:
        # Runs on an SDK thread. Never touch the queue directly from here.
        try:
            self._loop.call_soon_threadsafe(self.queue.put_nowait, change.key)
        except RuntimeError:
            # The event loop is already closed (server shutting down).
            log.debug("Dropped flag change for %s: event loop closed", change.key)

    def close(self) -> None:
        if not self._handles:
            return
        for handle in self._handles:
            self._tracker.remove_listener(handle)
        self._handles = []
        FlagSubscription.open_count -= 1

    # Number of live subscriptions, shown on /healthz to prove cleanup works.
    open_count = 0
