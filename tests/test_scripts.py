"""The experiment traffic simulator and the rollback script."""

import json
import random
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import ldclient
import pytest

from app import assistant
from app.flags import ASSISTANT_CONFIG
from app.settings import Settings
from scripts.explain import explain
from scripts.simulate_assistant import simulate as simulate_assistant
from scripts.simulate_traffic import simulate
from tests.conftest import ASSISTANT_VALUE, FAKE_MODEL_KEY, FAKE_SDK_KEY, assistant_config, hos

ROOT = Path(__file__).resolve().parent.parent


def test_explain_shows_each_value_and_why(ld):
    hos(ld, targets=True, rules=True)
    assistant_config(ld, enabled=True)
    rows = {(visitor, key): (value, reason) for visitor, key, value, reason in explain(ldclient.get())}
    assert len(rows) == 18  # 6 visitors x (2 flags + the AI Config)
    assert rows["quinn", "driver-hours-of-service"] == ('"off"', "FALLTHROUGH")
    assert rows["riley", "driver-hours-of-service"] == ('"us"', "TARGET_MATCH")
    assert rows["dana", "driver-hours-of-service"] == ('"canada"', "RULE_MATCH (rule 1)")
    assert rows["alex", "driver-hours-of-service"] == ('"off"', "FALLTHROUGH")
    assert rows["sam", "eta-predictions"] == ("false", "ERROR (FLAG_NOT_FOUND)")
    assert rows["sam", "dispatcher-assistant"] == ("concise (claude-haiku-5-5)", "FALLTHROUGH")


def test_simulated_visitors_land_in_the_us_enterprise_audience(ld):
    hos(ld, rules=True)
    results = simulate(ldclient.get(), 200, {"off": 0.0, "us": 1.0}, random.Random(1), "test")
    assert results == {"us": [200, 200]}


def test_simulator_converts_at_roughly_the_given_rate(ld):
    hos(ld, rules=True)
    seen, converted = simulate(ldclient.get(), 2000, {"us": 0.25}, random.Random(7), "test")["us"]
    assert seen == 2000
    assert 0.21 < converted / seen < 0.29


SETTINGS_WITH_MODEL = Settings(sdk_key=FAKE_SDK_KEY, model_api_key=FAKE_MODEL_KEY)


def test_assistant_simulator_measures_answers_on_the_default_rule(ld, monkeypatch):
    # The AI Config as in LaunchDarkly: enterprise gets friendly, everyone else the default rule.
    friendly = {
        **ASSISTANT_VALUE,
        "_ldMeta": {**ASSISTANT_VALUE["_ldMeta"], "variationKey": "friendly"},
        "model": {"name": "claude-sonnet-5-5", "parameters": {"max_tokens": 400}},
    }
    flag = ld.flag(ASSISTANT_CONFIG).variations(ASSISTANT_VALUE, friendly).fallthrough_variation(0)
    flag.if_match_context("organization", "plan", "enterprise").then_return(1)
    ld.update(flag)
    reply = assistant.ModelReply("On schedule.", 900, 40, "end_turn")
    monkeypatch.setattr(assistant, "_call_model", lambda *args: reply)

    results, errors = simulate_assistant(4, SETTINGS_WITH_MODEL, "test")

    # Synthetic dispatchers are self-serve, so each reaches the default rule, where the experiment runs.
    assert errors == 0 and list(results) == ["claude-haiku-5-5"]
    assert [usage["output_tokens"] for usage in results["claude-haiku-5-5"]] == [40] * 4


def test_assistant_simulator_counts_failed_answers(ld, monkeypatch):
    assistant_config(ld, enabled=True)

    def broken(*args):
        raise RuntimeError("provider down")

    monkeypatch.setattr(assistant, "_call_model", broken)
    assert simulate_assistant(3, SETTINGS_WITH_MODEL, "test") == ({}, 3)


@pytest.fixture
def fake_launchdarkly():
    """A local HTTP server that records requests, standing in for LaunchDarkly."""
    received = []

    class Handler(BaseHTTPRequestHandler):
        def _record(self):
            length = int(self.headers.get("Content-Length") or 0)
            received.append((self.command, self.path, dict(self.headers), self.rfile.read(length).decode()))
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"{}")

        do_POST = do_PATCH = _record

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}", received
    server.shutdown()


def run_rollback(tmp_path, env, *args):
    # Run a copy of the script so a developer's real .env is never read by the test.
    (tmp_path / "scripts").mkdir(exist_ok=True)
    copy = tmp_path / "scripts" / "rollback.sh"
    copy.write_text((ROOT / "scripts" / "rollback.sh").read_text())
    return subprocess.run(  # noqa: S603
        ["/bin/bash", str(copy), *args], env={"PATH": "/usr/bin:/bin", **env}, capture_output=True, text=True
    )


def test_rollback_requires_configuration(tmp_path):
    result = run_rollback(tmp_path, {})
    assert result.returncode == 1
    assert "Set LD_TRIGGER_URL" in result.stderr


def test_rollback_fires_the_trigger_and_is_repeatable(tmp_path, fake_launchdarkly):
    base, received = fake_launchdarkly
    env = {"LD_TRIGGER_URL": f"{base}/webhook/triggers/abc123/secret"}
    assert run_rollback(tmp_path, env).returncode == 0
    assert run_rollback(tmp_path, env).returncode == 0
    assert [(method, path) for method, path, _, _ in received] == [("POST", "/webhook/triggers/abc123/secret")] * 2


def test_rollback_falls_back_to_rest_semantic_patch(tmp_path, fake_launchdarkly):
    base, received = fake_launchdarkly
    env = {"LD_API_BASE": base, "LD_API_TOKEN": "api-test", "LD_PROJECT_KEY": "abc-freight", "LD_ENV_KEY": "test"}
    result = run_rollback(tmp_path, env, "driver-hours-of-service")
    assert result.returncode == 0, result.stderr
    method, path, headers, body = received[0]
    assert (method, path) == ("PATCH", "/api/v2/flags/abc-freight/driver-hours-of-service")
    assert headers["Authorization"] == "api-test"
    assert "domain-model=launchdarkly.semanticpatch" in headers["Content-Type"]
    assert json.loads(body)["instructions"] == [{"kind": "turnFlagOff"}]
    assert json.loads(body)["environmentKey"] == "test"
