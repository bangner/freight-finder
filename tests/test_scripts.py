"""The experiment traffic simulator and the rollback script."""

import json
import random
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import ldclient
import pytest

from scripts.simulate_traffic import simulate
from tests.conftest import hos

ROOT = Path(__file__).resolve().parent.parent


def test_simulated_visitors_land_in_the_us_enterprise_audience(ld):
    hos(ld, rules=True)
    results = simulate(ldclient.get(), 200, {"off": 0.0, "us": 1.0}, random.Random(1), "test")
    assert results == {"us": [200, 200]}


def test_simulator_converts_at_roughly_the_given_rate(ld):
    hos(ld, rules=True)
    seen, converted = simulate(ldclient.get(), 2000, {"us": 0.25}, random.Random(7), "test")["us"]
    assert seen == 2000
    assert 0.21 < converted / seen < 0.29


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
