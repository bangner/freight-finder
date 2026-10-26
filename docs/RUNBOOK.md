# Runbook

## Release

1. Deploy with the flag **off** and its default rule serving the old behavior.
2. Target your own organization (`abc-freight`), turn the flag on, and test as an internal user such as Quinn.
3. Release: change the default rule. Open pages update within a second.
4. Watch errors and Slack for 15 minutes.

## Roll back

Roll back first, investigate afterwards. No deploy, restart or page refresh is needed.

- **Dashboard:** toggle the flag **Off**.
- **Command line:** `scripts/rollback.sh` (the trigger) or `scripts/rollback.sh <flag-key>` (the REST API). Safe to repeat.
- **Without the repo:** `curl -X POST "$LD_TRIGGER_URL"`. A monitoring alert can call the same URL.
- **Check:** the flag shows Off with the trigger in its history, Slack posts the change, and `python scripts/explain.py` shows `OFF`.

## Retire a release flag

Once `eta-predictions` has served `true` to everyone long enough that nobody would roll it back (two weeks is common):

1. Delete the flag check and the `false` code path, then deploy.
2. Delete the flag from `terraform/flags.tf` and apply. LaunchDarkly archives it rather than deleting it.
3. Code references in LaunchDarkly confirm that nothing still uses the key.

Long-lived flags stay: `driver-hours-of-service` and `dispatcher-assistant`.

## Check for drift

- From `terraform/`, run `terraform plan`. "No changes" means every field Terraform manages matches the code. Targeting is handed to the UI, so the plan does not check it.
- Never apply a plan that destroys or replaces the project, an environment or the trigger: that deletes SDK keys or changes the trigger URL.

## Rotate secrets

| Secret | Rotate in | Then |
| --- | --- | --- |
| Trigger URL | Flag > Configuration in environment > Triggers > reset URL | Update `LD_TRIGGER_URL` |
| SDK key | Project settings > Environments > reset SDK key | Update `LAUNCHDARKLY_SDK_KEY` and restart |
| Access tokens | Account settings > Authorization | Update `LD_API_TOKEN` or `terraform/.env` |
| Model API key | Anthropic console | Update `MODEL_API_KEY` and restart |

## Health check

`GET /healthz` returns `{"status": "ok", "launchdarkly_initialized": true, "open_streams": 2}`. `launchdarkly_initialized: false` means every feature is serving its fallback: check the SDK key and network access.
