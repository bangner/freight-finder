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
| `tests/test_flags.py` | Fallbacks, both flags, the staged release to the internal tester, every visitor's targeting result and evaluation reason, the kill switch overriding targeting, private and anonymous contexts |
| `tests/test_live_updates.py` | Snapshot on connect, live push on change, only affected visitors updated, listeners removed on disconnect |
| `tests/test_api.py` | Endpoints, the simulated bad release, event tracking, the assistant (model, prompt and effort from the AI Config, dry run, cut-off and refused answers, metrics, feedback, failures), no secrets in any response |
| `tests/test_settings.py` | Clear failure on a missing or wrong SDK key, the dry-run switch |
| `tests/test_scripts.py` | Rollback through the trigger and the REST fallback (against a local fake server), repeatability, the traffic simulator, `explain.py` |
| `tests/e2e/test_browser.py` | Chromium on a real server: the full Part 1 demo (internal tester first, then everyone), Part 2 and the assistant, checking that the page never reloads |

CI runs the tests on Python 3.11, 3.12 and 3.13, the browser test, a gitleaks secret scan and a Docker build on every push.

## Manual test plan

Run against a real LaunchDarkly Test environment set up as in [LAUNCHDARKLY_SETUP.md](LAUNCHDARKLY_SETUP.md). Keep one browser tab open throughout and never refresh it. The page footer shows each flag's value and reason; `python scripts/explain.py` shows them for every visitor.

| # | Area | Steps | Expected |
| --- | --- | --- | --- |
| 1 | Startup | Remove `LAUNCHDARKLY_SDK_KEY` from `.env`, run `python -m app` | Exits with "LAUNCHDARKLY_SDK_KEY is not set" |
| 2 | Startup | Restore the key, run `python -m app`, open `/healthz` | `launchdarkly_initialized: true` |
| 3 | Evaluation | Open the page with `eta-predictions` off, default rule `false` | Loads table only; footer shows `eta-predictions: false OFF`; status shows Live |
| 4 | Test in production | Turn `eta-predictions` on | Guest still sees nothing (`FALLTHROUGH`); switch to Quinn: ETA panel shows (`TARGET_MATCH`) |
| 5 | Bad release | As Quinn, click **Refresh predictions** | Red "Prediction refresh failed … timed out" message |
| 6 | Release | Change the default rule to `true` | ETA panel appears for every visitor within about a second, no reload |
| 7 | Rollback | Run `scripts/rollback.sh` | Script prints success; panel disappears for every visitor in under a second; flag shows Off in LaunchDarkly. Then set the default rule back to `false` |
| 8 | Remediation is repeatable | Run `scripts/rollback.sh` again | Succeeds; nothing changes |
| 9 | Reconnect | Viewing as Quinn, stop the app, turn `eta-predictions` on, start the app again | Status shows Reconnecting, then Live; the panel appears on reconnect without a refresh |
| 10 | Individual target | Viewing as Riley, add the `lakeshore-logistics` target | HOS panel with US rules appears for Riley only; footer shows `TARGET_MATCH` |
| 11 | Rules | Add both enterprise rules; switch between Dana, Sam, Alex, Quinn, Guest | Dana: Canada rules; Sam: US rules (or no panel while the experiment runs and Lone Star Freight is in the control group); Alex, Quinn and Guest: no panel |
| 12 | Kill switch beats targeting | Turn `driver-hours-of-service` off | Panel disappears for everyone |
| 13 | Private attribute | Open the `user-dana` context in LaunchDarkly | `email` is not shown |
| 14 | Experiment | Click **Book a load**; run `scripts/simulate_traffic.py --visitors 2500 --seed 2026` | Metric receives events; experiment results show `us` ahead of `off` (see [EXPERIMENT.md](EXPERIMENT.md)) |
| 15 | AI Config, dry run | Without `MODEL_API_KEY`, ask a question as Sam | Answer starts "Dry run: no model was called" and shows the model, `max_tokens` and prompt LaunchDarkly served |
| 16 | AI Config | Set `MODEL_API_KEY`, ask a question as Sam, switch Sam's variation, ask again | The assistant panel shows the new model and the tone changes, with no restart |
| 17 | AI metrics | Click thumbs up | Monitoring tab shows tokens, latency, and positive feedback |
| 18 | Cleanup | Close the tab, open `/healthz` | `open_streams` drops by one |
| 19 | Slack | Run the rollback with Slack subscribed | The channel shows the change |
