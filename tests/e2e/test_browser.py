"""End-to-end: a real browser on a real server, flags flipped while the page stays open.

Skipped unless Playwright is installed:
    pip install -r requirements-dev.txt playwright && python -m playwright install chromium
    pytest tests/e2e

Set SCREENSHOT_DIR=docs/images to refresh the README screenshots.
Set CHROMIUM_PATH to use an already-installed Chromium.
"""

import os
import socket
import threading
import time
from pathlib import Path

import pytest
import uvicorn

from app import assistant
from tests.conftest import FAKE_MODEL_KEY, FAKE_SDK_KEY, assistant_config, eta, hos, ld_test_config

sync_api = pytest.importorskip("playwright.sync_api")

from app.main import create_app  # noqa: E402
from app.settings import Settings  # noqa: E402

TIMEOUT_MS = 3000  # "instant" for the purposes of this test


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def server(td, monkeypatch):
    answer = "LSF-1041 is running about 22 minutes late because of heavy traffic."
    monkeypatch.setattr(assistant, "_call_model", lambda *a: assistant.ModelReply(answer, 90, 14, "end_turn"))
    app = create_app(ld_test_config(td), Settings(sdk_key=FAKE_SDK_KEY, model_api_key=FAKE_MODEL_KEY))
    port = _free_port()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", timeout_graceful_shutdown=1)
    srv = uvicorn.Server(config)
    thread = threading.Thread(target=srv.run, daemon=True)
    thread.start()
    deadline = time.time() + 10
    while not srv.started:
        if time.time() > deadline:
            raise RuntimeError("server did not start")
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}"
    srv.should_exit = True
    thread.join(5)


@pytest.fixture
def page():
    with sync_api.sync_playwright() as p:
        try:
            browser = p.chromium.launch(executable_path=os.environ.get("CHROMIUM_PATH") or None)
        except sync_api.Error as error:
            if "Executable doesn't exist" in str(error):
                pytest.skip("No Chromium found: run `python -m playwright install chromium` or set CHROMIUM_PATH")
            raise
        page = browser.new_page(viewport={"width": 1200, "height": 900})
        yield page
        browser.close()


def shot(page, name: str) -> None:
    directory = os.environ.get("SCREENSHOT_DIR")
    if directory:
        Path(directory).mkdir(parents=True, exist_ok=True)
        page.wait_for_timeout(1300)  # let the "feature arrived" highlight fade
        page.screenshot(path=f"{directory}/{name}.png", full_page=True)


def test_release_rollback_targeting_and_assistant_without_reload(server, td, page):
    expect = sync_api.expect
    eta(td, False)
    hos(td)

    page.goto(server)
    expect(page.locator("#live-text")).to_have_text("Live", timeout=TIMEOUT_MS)
    expect(page.locator("#eta-panel")).to_be_hidden()
    # Anything stored on window survives only if the page never reloads.
    page.evaluate("window.__sameDocument = true")
    shot(page, "1-original")

    # Part 1: test in production. Only ABC Freight's own QA tester sees it first.
    eta(td, True, internal_only=True)
    page.select_option("#visitor-select", "quinn")
    expect(page.locator("#eta-panel")).to_be_visible(timeout=TIMEOUT_MS)
    expect(page.locator("#flag-values")).to_contain_text("eta-predictions: true TARGET_MATCH")
    page.select_option("#visitor-select", "guest")
    expect(page.locator("#eta-panel")).to_be_hidden(timeout=TIMEOUT_MS)

    # Then release to everyone from the dashboard.
    eta(td, True)
    expect(page.locator("#eta-panel")).to_be_visible(timeout=TIMEOUT_MS)
    expect(page.locator("#eta-body tr")).to_have_count(5)
    shot(page, "2-eta-on")

    # The problem release.
    page.click("#eta-refresh")
    expect(page.locator("#eta-error")).to_contain_text("timed out", timeout=TIMEOUT_MS)
    shot(page, "3-eta-error")

    # Remediation: the trigger turns the flag off.
    eta(td, False)
    expect(page.locator("#eta-panel")).to_be_hidden(timeout=TIMEOUT_MS)
    assert page.evaluate("window.__sameDocument") is True

    # Part 2: targeting. Dana is enterprise in Canada.
    page.select_option("#visitor-select", "dana")
    expect(page.locator("#greeting")).to_have_text("Welcome back, Dana", timeout=TIMEOUT_MS)
    expect(page.locator("#hos-panel")).to_be_hidden()
    hos(td, targets=True, rules=True)
    expect(page.locator("#hos-rules")).to_have_text("Rules: Canada (south of 60°N)", timeout=TIMEOUT_MS)
    # The footer says why: Dana matched the first targeting rule.
    expect(page.locator("#flag-values")).to_contain_text('driver-hours-of-service: "canada" RULE_MATCH (rule 1)')
    shot(page, "4-hos-canada")

    page.select_option("#visitor-select", "sam")
    expect(page.locator("#hos-rules")).to_have_text("Rules: US (FMCSA)", timeout=TIMEOUT_MS)
    page.select_option("#visitor-select", "alex")
    expect(page.locator("#greeting")).to_have_text("Welcome back, Alex", timeout=TIMEOUT_MS)
    expect(page.locator("#hos-panel")).to_be_hidden()

    # Kill switch beats targeting.
    page.select_option("#visitor-select", "dana")
    expect(page.locator("#hos-panel")).to_be_visible(timeout=TIMEOUT_MS)
    hos(td, on=False, targets=True, rules=True)
    expect(page.locator("#hos-panel")).to_be_hidden(timeout=TIMEOUT_MS)

    # Experimentation: the conversion button.
    page.click("#book-load")
    expect(page.locator("#book-confirm")).to_be_visible()

    # AI Config: turning it on in LaunchDarkly shows the assistant live.
    page.select_option("#visitor-select", "sam")
    assistant_config(td, enabled=True)
    expect(page.locator("#assistant-panel")).to_be_visible(timeout=TIMEOUT_MS)
    expect(page.locator("#assistant-model")).to_have_text("Model: claude-haiku-5-5")
    page.fill("#assistant-input", "Which loads are running late?")
    page.click("#assistant-form button[type=submit]")
    expect(page.locator("#assistant-text")).to_contain_text("22 minutes late", timeout=TIMEOUT_MS)
    page.click(".feedback button[data-positive=true]")
    expect(page.locator("#assistant-thanks")).to_be_visible(timeout=TIMEOUT_MS)
    shot(page, "5-assistant")

    assert page.evaluate("window.__sameDocument") is True
