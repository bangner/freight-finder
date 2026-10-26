"""HTTP endpoints, the simulated bad release, tracking, the assistant, and secret handling."""

import pytest

from app import assistant
from tests.conftest import FAKE_MODEL_KEY, FAKE_SDK_KEY, assistant_config, eta, make_client


def test_healthz(client):
    body = client.get("/healthz").json()
    assert body["status"] == "ok"
    assert body["launchdarkly_initialized"] is True


def test_page_and_assets_are_served(client):
    assert "ABC Freight" in client.get("/").text
    assert client.get("/static/app.js").status_code == 200


def test_visitor_list_has_no_email(client):
    visitors = client.get("/api/visitors").json()
    assert {v["key"] for v in visitors} == {"dana", "sam", "riley", "alex", "quinn", "guest"}
    assert all("email" not in v for v in visitors)


def test_eta_refresh_is_404_when_flag_off(client, td):
    eta(td, False)
    assert client.post("/api/eta/refresh?visitor=sam").status_code == 404


def test_eta_refresh_shows_the_simulated_bug_when_flag_on(client, td):
    eta(td, True)
    response = client.post("/api/eta/refresh?visitor=sam")
    assert response.status_code == 502
    assert "timed out" in response.json()["detail"]


def test_track_accepts_only_known_events(client):
    assert client.post("/api/track", json={"visitor": "sam", "event": "book-load-clicked"}).status_code == 202
    assert client.post("/api/track", json={"visitor": "sam", "event": "anything"}).status_code == 400


def must_not_call_the_model(*args):
    raise AssertionError("a dry run must not call the model")


def test_assistant_runs_dry_without_model_key(client, td, monkeypatch):
    assistant_config(td, enabled=True)
    monkeypatch.setattr(assistant, "_call_model", must_not_call_the_model)
    assert client.get("/api/state?visitor=sam").json()["assistant"] == {
        "enabled": True,
        "model": "claude-haiku-5-5",
        "dry_run": True,
    }
    body = client.post("/api/assistant", json={"visitor": "sam", "question": "hi"}).json()
    assert body["dry_run"] is True and body["feedback_token"] is None and body["usage"] is None
    assert body["answer"].startswith("Dry run: no model was called. LaunchDarkly served claude-haiku-5-5")
    assert "Lone Star Freight" in body["answer"]  # the prompt LaunchDarkly served, variables filled in


def test_dry_run_can_be_forced_with_a_key(td, monkeypatch):
    assistant_config(td, enabled=True)
    monkeypatch.setattr(assistant, "_call_model", must_not_call_the_model)
    with make_client(td, FAKE_MODEL_KEY, assistant_dry_run=True) as client:
        body = client.post("/api/assistant", json={"visitor": "sam", "question": "hi"}).json()
    assert body["dry_run"] is True


def test_assistant_disabled_config_returns_503(client_with_model, td):
    assistant_config(td, enabled=False)
    assert client_with_model.get("/api/state?visitor=sam").json()["assistant"]["enabled"] is False
    assert client_with_model.post("/api/assistant", json={"visitor": "sam", "question": "hi"}).status_code == 503


def test_assistant_uses_model_and_prompt_from_launchdarkly(client_with_model, td, monkeypatch):
    assistant_config(td, enabled=True)
    calls = []

    def fake_model(api_key, model, max_tokens, effort, system, messages):
        calls.append((api_key, model, max_tokens, effort, system, messages))
        return assistant.ModelReply("Load LSF-1042 is on schedule.", 120, 12, "end_turn")

    monkeypatch.setattr(assistant, "_call_model", fake_model)

    assert client_with_model.get("/api/state?visitor=sam").json()["assistant"] == {
        "enabled": True,
        "model": "claude-haiku-5-5",
        "dry_run": False,
    }
    body = client_with_model.post("/api/assistant", json={"visitor": "sam", "question": "Where is 1042?"}).json()

    assert body["answer"] == "Load LSF-1042 is on schedule."
    assert body["model"] == "claude-haiku-5-5"
    assert body["dry_run"] is False
    assert body["usage"]["input_tokens"] == 120 and body["usage"]["output_tokens"] == 12
    assert body["usage"]["duration_ms"] >= 0
    api_key, model, max_tokens, effort, system, messages = calls[0]
    assert (api_key, model, max_tokens, effort) == (FAKE_MODEL_KEY, "claude-haiku-5-5", 300, None)
    assert "Lone Star Freight" in system and "LSF-1042" in system  # prompt variables filled in
    assert messages == [{"role": "user", "content": "Where is 1042?"}]

    feedback = {"visitor": "sam", "feedback_token": body["feedback_token"], "positive": True}
    assert client_with_model.post("/api/assistant/feedback", json=feedback).status_code == 202


def test_assistant_model_failure_returns_502(client_with_model, td, monkeypatch):
    assistant_config(td, enabled=True)

    def broken(*args):
        raise RuntimeError("provider down")

    monkeypatch.setattr(assistant, "_call_model", broken)
    assert client_with_model.post("/api/assistant", json={"visitor": "sam", "question": "hi"}).status_code == 502


@pytest.mark.parametrize(
    ("reply", "message"),
    [
        (assistant.ModelReply("LSF-1041 is running", 100, 300, "max_tokens"), "cut off at max_tokens 300"),
        (assistant.ModelReply("", 100, 5, "refusal"), "declined"),
        (assistant.ModelReply("  ", 100, 5, "end_turn"), "empty answer"),
    ],
)
def test_unusable_answers_are_explained_not_shown(client_with_model, td, monkeypatch, reply, message):
    assistant_config(td, enabled=True)
    monkeypatch.setattr(assistant, "_call_model", lambda *args: reply)
    response = client_with_model.post("/api/assistant", json={"visitor": "sam", "question": "hi"})
    assert response.status_code == 502
    assert message in response.json()["detail"]


@pytest.mark.parametrize(("configured", "sent"), [("low", "low"), ("extreme", None)])
def test_effort_comes_from_the_ai_config(client_with_model, td, monkeypatch, configured, sent):
    assistant_config(td, enabled=True, effort=configured)
    efforts = []

    def fake_model(api_key, model, max_tokens, effort, system, messages):
        efforts.append(effort)
        return assistant.ModelReply("On schedule.", 100, 10, "end_turn")

    monkeypatch.setattr(assistant, "_call_model", fake_model)
    client_with_model.post("/api/assistant", json={"visitor": "sam", "question": "hi"})
    assert efforts == [sent]  # an unknown effort level is ignored, not sent to the model


def test_bad_feedback_token_is_rejected(client):
    feedback = {"visitor": "sam", "feedback_token": "not-a-token", "positive": False}
    assert client.post("/api/assistant/feedback", json=feedback).status_code == 400


@pytest.mark.parametrize("path", ["/", "/static/app.js", "/api/visitors", "/api/state?visitor=sam", "/healthz"])
def test_no_secret_reaches_the_browser(td, path):
    assistant_config(td, enabled=True)
    with make_client(td, FAKE_MODEL_KEY) as client:
        text = client.get(path).text
    assert FAKE_SDK_KEY not in text
    assert FAKE_MODEL_KEY not in text
