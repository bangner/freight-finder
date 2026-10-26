# Runbook

For whoever is on call during a release of ABC Freight.

## Release a feature

1. Deploy with the feature's flag **off** and its default rule serving the old behavior. Both code paths ship together; the deploy changes nothing users see.
2. Target your own organization (individual target `abc-freight`), turn the flag on, and check the feature in production as an internal user, such as the Quinn visitor.
3. Release: change the default rule, or widen the rules. Open browsers update within about a second.
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
3. An open page has lost the feature without a refresh. The footer bar shows the flag's current value and the reason `OFF`. `python scripts/explain.py` shows every visitor at once.
4. `curl -s localhost:8000/api/state?visitor=sam` shows `"eta": null`.

## Retire a release flag

A release flag is temporary. Once `eta-predictions` has served `true` to every customer long enough that nobody would roll it back (two weeks is a common rule), remove it:

1. In the code, delete the flag check and the code path for `false`: the `ETA_FLAG` gate in `app/main.py`, its entries in `app/flags.py`, the check in `/api/eta/refresh`, and the tests for the off state.
2. Deploy. The feature now runs without asking LaunchDarkly.
3. Archive the flag: delete its resources from `terraform/flags.tf` and run `terraform apply`, which archives it rather than deleting it. Do this after the deploy: code that still evaluates an archived flag gets its fallback value, `false`, and the feature would disappear. LaunchDarkly's code references (setup guide, step 9) confirm no code still uses the key.

Long-lived flags stay: `driver-hours-of-service` decides which rule set each customer gets, and `dispatcher-assistant` holds the assistant's model and prompt.

## Check for drift

The LaunchDarkly setup is Terraform code ([terraform/README.md](../terraform/README.md)). From `terraform/`, with the access token exported, run `terraform plan`. "No changes" means LaunchDarkly matches the code. Targeting changes never show up: Terraform hands targeting to LaunchDarkly after creating it, so releases and rollbacks are not drift.

Never apply a plan that destroys or replaces the project, an environment or the trigger. That would delete SDK keys or change the trigger URL.

## Rotate secrets

| Secret | Where to rotate | Then |
| --- | --- | --- |
| Trigger URL | Flag > Configuration in environment > Triggers > the trigger's menu > reset URL | Update `LD_TRIGGER_URL`. No restart needed; the script reads `.env` each run. |
| API access token | Account settings > Authorization | Update `LD_API_TOKEN`. |
| Terraform access token | Account settings > Authorization | Update `terraform/.env`. |
| SDK key | Project settings > Environments > reset the SDK key (LaunchDarkly can keep the old key valid for a grace period) | Update `LAUNCHDARKLY_SDK_KEY` and restart the app. |
| Model API key | Your Anthropic console | Update `MODEL_API_KEY` and restart the app. |

## Health check

`GET /healthz` returns:

```json
{"status": "ok", "launchdarkly_initialized": true, "open_streams": 2}
```

`launchdarkly_initialized: false` means the app is serving fallbacks (every feature off). Check the SDK key and network access to LaunchDarkly. `open_streams` is the number of connected browsers and should drop back when tabs close.
