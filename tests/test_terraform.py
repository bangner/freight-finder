"""The Terraform code must create the flags the app evaluates and count the events it sends."""

import re
from pathlib import Path

from app.flags import ASSISTANT_CONFIG, ETA_FLAG, HOS_FLAG
from app.main import ALLOWED_EVENTS

TERRAFORM_DIR = Path(__file__).resolve().parent.parent / "terraform"
TERRAFORM = "\n".join(path.read_text() for path in sorted(TERRAFORM_DIR.glob("*.tf")))


def declared(argument: str) -> set[str]:
    """Every string literal assigned to this argument in terraform/*.tf."""
    return set(re.findall(rf'^\s*{argument}\s*=\s*"([^"]+)"', TERRAFORM, re.MULTILINE))


def test_terraform_creates_every_flag_the_app_evaluates():
    assert {ETA_FLAG, HOS_FLAG, ASSISTANT_CONFIG} <= declared("key")


def test_terraform_metrics_count_the_events_the_app_sends():
    # $ld:ai:* events come from the AI SDK; every other metric must count an event the app sends.
    app_events = {key for key in declared("event_key") if not key.startswith("$ld:")}
    assert app_events == ALLOWED_EVENTS
