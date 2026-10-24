# Testing

## Automated tests

```bash
pip install -r requirements-dev.txt
pytest                      # everything except the browser test, about 3 s
pytest tests/e2e            # real browser; needs: python -m playwright install chromium
ruff check . && ruff format --check .
```

No LaunchDarkly account, key or network access is needed. The tests use the SDK's `TestData` source to play the part of LaunchDarkly.

One detail matters here. `TestData` normally writes straight into the SDK's flag store, which skips the change notifications that a real streaming connection produces, so flag listeners would never fire. `tests/conftest.py` routes `TestData` through `config.data_source_update_sink`, the same path the streaming data source uses. That way the listener-to-SSE bridge is tested the way it runs in production.

| File | Covers |
| --- | --- |
| `tests/test_flags.py` | Fallbacks, both flags, every visitor's targeting result, the kill switch overriding targeting, private and anonymous contexts |
| `tests/test_live_updates.py` | Snapshot on connect, live push on change, only affected visitors updated, listeners removed on disconnect |
| `tests/test_api.py` | Endpoints, the simulated bad release, event tracking, the assistant (model and prompt from the AI Config, metrics, feedback, failures), no secrets in any response |
| `tests/test_settings.py` | Clear failure on a missing or wrong SDK key |
| `tests/test_scripts.py` | Rollback through the trigger and the REST fallback (against a local fake server), repeatability, the traffic simulator |
| `tests/e2e/test_browser.py` | Chromium on a real server: the full Part 1 and Part 2 demo and the assistant, checking that the page never reloads |

CI runs the tests on Python 3.11, 3.12 and 3.13, the browser test, a gitleaks secret scan and a Docker build on every push.

## Manual test plan

Run against a real LaunchDarkly Test environment set up as in [LAUNCHDARKLY_SETUP.md](LAUNCHDARKLY_SETUP.md). Keep one browser tab open throughout and never refresh it.

| # | Area | Steps | Expected |
| --- | --- | --- | --- |
| 1 | Startup | Remove `LAUNCHDARKLY_SDK_KEY` from `.env`, run `python -m app` | Exits with "LAUNCHDARKLY_SDK_KEY is not set" |
| 2 | Startup | Restore the key, run `python -m app`, open `/healthz` | `launchdarkly_initialized: true` |
| 3 | Evaluation | Open the page with `eta-predictions` off | Loads table only; footer shows `eta-predictions: false`; status shows Live |
| 4 | Activation | Turn `eta-predictions` on in LaunchDarkly | ETA panel appears within about a second, no reload |
| 5 | Bad release | Click **Refresh predictions** | Red "Prediction refresh failed … timed out" message |
| 6 | Rollback | Run `scripts/rollback.sh` | Script prints success; panel disappears; flag shows Off in LaunchDarkly |
| 7 | Remediation is repeatable | Run `scripts/rollback.sh` again | Succeeds; nothing changes |
| 8 | Reconnect | Stop the app, turn `eta-predictions` on, start the app again | Status shows Reconnecting, then Live; the panel appears on reconnect without a refresh |
| 9 | Individual target | Viewing as Riley, add the `lakeshore-logistics` target | HOS panel with US rules appears for Riley only |
| 10 | Rules | Add both enterprise rules; switch between Dana, Sam, Alex, Guest | Dana: Canada rules; Sam: US rules; Alex and Guest: no panel |
| 11 | Kill switch beats targeting | Turn `driver-hours-of-service` off | Panel disappears for everyone |
| 12 | Private attribute | Open the `user-dana` context in LaunchDarkly | `email` is not shown |
| 13 | Experiment | Click **Book a load**; run `scripts/simulate_traffic.py --visitors 500` | Metric receives events; experiment results show both variations |
| 14 | AI Config | Set `MODEL_API_KEY`, ask a question as Sam, switch Sam's variation, ask again | The assistant panel shows the new model and the tone changes, with no restart |
| 15 | AI metrics | Click thumbs up | Monitoring tab shows tokens, latency, and positive feedback |
| 16 | Cleanup | Close the tab, open `/healthz` | `open_streams` drops by one |
| 17 | Slack | Run the rollback with Slack subscribed | The channel shows the change |
