"""Flag evaluation and targeting: what each visitor sees for each flag setup."""

import pytest

from app.contexts import VISITORS, build_context, get_visitor
from app.main import build_state
from app.settings import Settings
from tests.conftest import FAKE_SDK_KEY, eta, hos

SETTINGS = Settings(sdk_key=FAKE_SDK_KEY, model_api_key=None)


def test_missing_flags_fall_back_to_original_ui(ld):
    state = build_state("sam", SETTINGS)
    assert state["flags"] == {"eta-predictions": False, "driver-hours-of-service": "off"}
    assert state["eta"] is None
    assert state["hos"] is None
    assert state["assistant"] == {"enabled": False, "model": None}
    assert len(state["loads"]) == 5


def test_eta_flag_on_adds_predictions(ld):
    eta(ld, True)
    state = build_state("guest", SETTINGS)
    assert [p["load_id"] for p in state["eta"]] == [load["id"] for load in state["loads"]]


def test_eta_flag_off_removes_predictions(ld):
    eta(ld, True)
    eta(ld, False)
    assert build_state("guest", SETTINGS)["eta"] is None


@pytest.mark.parametrize(
    ("visitor", "expected"),
    [("dana", "canada"), ("sam", "us"), ("riley", "us"), ("alex", "off"), ("guest", "off")],
)
def test_hos_targeting_matches_the_visitor_table(ld, visitor, expected):
    hos(ld, targets=True, rules=True)
    state = build_state(visitor, SETTINGS)
    assert state["flags"]["driver-hours-of-service"] == expected
    assert (state["hos"] is None) == (expected == "off")
    if state["hos"]:
        assert state["hos"]["ruleset"] == expected


def test_individual_target_alone_reaches_only_that_organization(ld):
    hos(ld, targets=True)
    values = {key: build_state(key, SETTINGS)["flags"]["driver-hours-of-service"] for key in VISITORS}
    assert values == {"dana": "off", "sam": "off", "riley": "us", "alex": "off", "guest": "off"}


def test_flag_off_overrides_targets_and_rules(ld):
    hos(ld, on=False, targets=True, rules=True)
    assert all(build_state(key, SETTINGS)["hos"] is None for key in VISITORS)


def test_canadian_rules_allow_more_driving_than_us_rules(ld):
    hos(ld, rules=True)
    us = build_state("sam", SETTINGS)["hos"]["drivers"]
    canada = build_state("dana", SETTINGS)["hos"]["drivers"]
    # Fourth driver has driven 10h15m: 45 min left under US rules, 2h45m under Canadian rules.
    assert us[3]["drive_left"] == "0h 45m" and us[3]["status"] == "under 1 hour"
    assert canada[3]["drive_left"] == "2h 45m" and canada[3]["status"] == "ok"
    assert us[3]["break_due_in"] == "0h 15m" and canada[3]["break_due_in"] is None


def test_email_is_private_and_guest_is_anonymous():
    dana = build_context(VISITORS["dana"])
    user = dana.get_individual_context("user")
    assert "email" in list(user.private_attributes)
    org = dana.get_individual_context("organization")
    assert org.get("plan") == "enterprise" and org.get("region") == "CA"
    assert build_context(VISITORS["guest"]).get_individual_context("user").anonymous


def test_unknown_visitor_falls_back_to_guest():
    assert get_visitor("nobody").key == "guest"
    assert get_visitor(None).key == "guest"
