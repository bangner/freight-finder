# Runbook

For whoever is on call during a release of ABC Freight.

## Release a feature

1. Deploy with the feature's flag **off**. Both code paths ship together; the deploy changes nothing users see.
2. Optional: target your own organization first (individual target) and check the feature in production.
3. Turn the flag on in LaunchDarkly, or widen its rules. Open browsers update within about a second.
4. Watch errors and the Slack channel for the next 15 minutes.

## Roll back

Roll back first and investigate afterwards. Rolling back does not need a deploy, a restart or a page refresh.

**Dashboard:** open the flag and toggle it **Off** in the affected environment.

**Command line** (from the repo, with `.env` filled in):

```bash
scripts/rollback.sh                           # eta-predictions, through the flag trigger
scripts/rollback.sh driver-hours-of-service   # any flag, through the REST API
```

The script exits non-zero if LaunchDarkly rejects the request. Running it again on a flag that is already off changes nothing. Without the repo, the trigger alone is enough:

```bash
curl -X POST "$LD_TRIGGER_URL"
```

A monitoring tool can call the same trigger URL when an alert fires, which turns the rollback into an automatic one.

## Verify a rollback

1. The flag shows **Off** in LaunchDarkly, and its history names the trigger or token that turned it off.
2. Slack shows the change, if the integration is set up.
3. An open page has lost the feature without a refresh. The footer bar shows the flag's current value.
4. `curl -s localhost:8000/api/state?visitor=sam` shows `"eta": null`.

## Rotate secrets

| Secret | Where to rotate | Then |
| --- | --- | --- |
| Trigger URL | Flag > Configuration in environment > Triggers > the trigger's menu > reset URL | Update `LD_TRIGGER_URL`. No restart needed; the script reads `.env` each run. |
| API access token | Account settings > Authorization | Update `LD_API_TOKEN`. |
| SDK key | Project settings > Environments > reset the SDK key (LaunchDarkly can keep the old key valid for a grace period) | Update `LAUNCHDARKLY_SDK_KEY` and restart the app. |
| Model API key | Your Anthropic console | Update `MODEL_API_KEY` and restart the app. |

## Health check

`GET /healthz` returns:

```json
{"status": "ok", "launchdarkly_initialized": true, "open_streams": 2}
```

`launchdarkly_initialized: false` means the app is serving fallbacks (every feature off). Check the SDK key and network access to LaunchDarkly. `open_streams` is the number of connected browsers and should drop back when tabs close.
