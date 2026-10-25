"""Flag evaluation and targeting: what each visitor sees for each flag setup."""

import pytest

from app.contexts import VISITORS, build_context, get_visitor
from app.flags import describe_reason
from app.main import build_state
from app.settings import Settings
from tests.conftest import FAKE_SDK_KEY, eta, hos

SETTINGS = Settings(sdk_key=FAKE_SDK_KEY, model_api_key=None)


def test_missing_flags_fall_back_to_original_ui(ld):
    state = build_state("sam", SETTINGS)
    assert state["flags"] == {"eta-predictions": False, "driver-hours-of-service": "off"}
    assert state["reasons"] == {
        "eta-predictions": "ERROR (FLAG_NOT_FOUND)",
        "driver-hours-of-service": "ERROR (FLAG_NOT_FOUND)",
    }
    assert state["eta"] is None
    assert state["hos"] is None
    assert state["assistant"] == {"enabled": False, "model": None, "dry_run": True}
    assert len(state["loads"]) == 5


def test_eta_flag_on_adds_predictions(ld):
    eta(ld, True)
    state = build_state("guest", SETTINGS)
    assert [p["load_id"] for p in state["eta"]] == [load["id"] for load in state["loads"]]


def test_eta_flag_off_removes_predictions(ld):
    eta(ld, True)
    eta(ld, False)
    assert build_state("guest", SETTINGS)["eta"] is None


def test_staged_release_reaches_only_the_internal_tester(ld):
    eta(ld, True, internal_only=True)
    states = {key: build_state(key, SETTINGS) for key in VISITORS}
    assert {key: state["flags"]["eta-predictions"] for key, state in states.items()} == {
        "dana": False,
        "sam": False,
        "riley": False,
        "alex": False,
        "quinn": True,
        "guest": False,
    }
    assert states["quinn"]["reasons"]["eta-predictions"] == "TARGET_MATCH"
    assert states["quinn"]["eta"] is not None
    assert states["sam"]["reasons"]["eta-predictions"] == "FALLTHROUGH"
    assert states["sam"]["eta"] is None


@pytest.mark.parametrize(
    ("visitor", "expected", "reason"),
    [
        ("dana", "canada", "RULE_MATCH (rule 1)"),
        ("sam", "us", "RULE_MATCH (rule 2)"),
        ("riley", "us", "TARGET_MATCH"),
        ("alex", "off", "FALLTHROUGH"),
        ("quinn", "off", "FALLTHROUGH"),  # internal plan: matches neither rule, so stays out of the experiment
        ("guest", "off", "FALLTHROUGH"),
    ],
)
def test_hos_targeting_matches_the_visitor_table(ld, visitor, expected, reason):
    hos(ld, targets=True, rules=True)
    state = build_state(visitor, SETTINGS)
    assert state["flags"]["driver-hours-of-service"] == expected
    assert state["reasons"]["driver-hours-of-service"] == reason
    assert (state["hos"] is None) == (expected == "off")
    if state["hos"]:
        assert state["hos"]["ruleset"] == expected


def test_individual_target_alone_reaches_only_that_organization(ld):
    hos(ld, targets=True)
    values = {key: build_state(key, SETTINGS)["flags"]["driver-hours-of-service"] for key in VISITORS}
    assert values == {"dana": "off", "sam": "off", "riley": "us", "alex": "off", "quinn": "off", "guest": "off"}


def test_flag_off_overrides_targets_and_rules(ld):
    hos(ld, on=False, targets=True, rules=True)
    states = [build_state(key, SETTINGS) for key in VISITORS]
    assert all(state["hos"] is None for state in states)
    assert all(state["reasons"]["driver-hours-of-service"] == "OFF" for state in states)


def test_reasons_are_described_in_a_few_words():
    in_experiment = {"kind": "RULE_MATCH", "ruleIndex": 1, "ruleId": "r2", "inExperiment": True}
    assert describe_reason(in_experiment) == "RULE_MATCH (rule 2, in experiment)"
    assert describe_reason({"kind": "PREREQUISITE_FAILED", "prerequisiteKey": "eta-predictions"}) == (
        "PREREQUISITE_FAILED (eta-predictions)"
    )
    assert describe_reason({"kind": "OFF"}) == "OFF"
    assert describe_reason(None) == "unknown"


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
