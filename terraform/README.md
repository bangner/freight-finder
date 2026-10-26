# LaunchDarkly setup with Terraform

This folder creates the LaunchDarkly side of ABC Freight with LaunchDarkly's [Terraform provider](https://registry.terraform.io/providers/launchdarkly/launchdarkly/latest). It replaces most of the clicks in [docs/LAUNCHDARKLY_SETUP.md](../docs/LAUNCHDARKLY_SETUP.md), which stays the reference for every setting and covers what Terraform cannot do.

| Terraform creates | You do in LaunchDarkly |
| --- | --- |
| Project `abc-freight` with Test and Production (Production asks for a comment and a confirmation on every change) | AI Config targeting: the provider has no resource for it |
| Context kind `organization` | Mark `organization` "Available for experiments": the provider cannot set it |
| Flags `eta-predictions` and `driver-hours-of-service`, with their starting targeting in Test | The two experiments, optional: the provider has no resource for experiments |
| The trigger that turns `eta-predictions` off | Slack, optional |
| The three experiment metrics, each with the right "better" direction | |
| AI Config `dispatcher-assistant` with its `concise` and `friendly` variations: models, `max_tokens`, prompts | |

## Before you start

- Terraform 1.7 or newer.
- A LaunchDarkly access token with the **Admin** role (**Account settings > Authorization**). A new project needs a context kind, and the Writer role is not allowed to create one.
- Put the token in `terraform/.env`, never in the app's `.env`: the app never needs it, and Docker passes that file to the web process.

## Build it

```bash
cd terraform
cp .env.example .env           # paste the token after LAUNCHDARKLY_ACCESS_TOKEN=
set -a && . ./.env && set +a   # export it to this shell
terraform init
terraform apply                # read the plan, then type yes
```

Then finish in this order:

1. **Keys for the app.** Each command prints one secret; paste it into the repo's `.env`.
   ```bash
   terraform output -raw sdk_key       # LAUNCHDARKLY_SDK_KEY
   terraform output -raw trigger_url   # LD_TRIGGER_URL
   ```
2. **AI Config targeting.** Open **AI Configs > dispatcher-assistant > Targeting** in Test. Check it is on with the default rule serving `concise`. Add a custom rule: context kind `organization`, attribute `plan`, **is one of** `enterprise`, serve `friendly`.
3. **Experiments, optional.** Mark `organization` "Available for experiments" (**Contexts**, gear icon). Then create the booking metric with a second apply, and the experiments as in steps 6 and 7 of the setup guide:
   ```bash
   terraform apply -var create_booking_metric=true
   ```
   To keep that setting for later applies, put `create_booking_metric = true` in `terraform.tfvars` (git-ignored).

No Enterprise plan? Flag triggers need one. Add `-var create_trigger=false` to every apply and use the REST fallback in `scripts/rollback.sh`.

`python scripts/explain.py` then shows every visitor's values and reasons; they should match the visitor table in the main README.

## What Terraform owns afterwards

- **Definitions are code.** Variations, descriptions, the temporary marker, metrics, models and prompts change here, get reviewed in a pull request, and reach LaunchDarkly with `terraform apply`. Each object carries the tag `managed-by-terraform`, so people can see in LaunchDarkly what not to change by hand.
- **Targeting belongs to LaunchDarkly.** Terraform creates each flag's starting targeting, then ignores it (`lifecycle { ignore_changes = all }`). Releasing, rolling back with the trigger and running experiments happen in LaunchDarkly, and a later apply never undoes them. [ADR 0006](../docs/decisions/0006-launchdarkly-configuration-as-code.md) explains the split.
- **Drift check.** `terraform plan` saying "No changes" means LaunchDarkly matches the code. Never apply a plan that destroys or replaces the project, an environment or the trigger: that would delete SDK keys or change the trigger URL.

## Adopt a project you built by hand

If you followed the setup guide by hand, Terraform can take the project over without recreating anything. This repo's own demo project was adopted this way.

1. `cp imports.tf.example imports.tf` and set `trigger_id` (the file shows how to look it up). Check the metric keys under **Metrics**.
2. If the booking metric exists, put `create_booking_metric = true` in `terraform.tfvars`.
3. `terraform plan`. It is read-only. It lists what it would import and change; apply only if it destroys and replaces nothing.
4. `terraform apply`, then `terraform plan` again: it should report "No changes". Delete `imports.tf`.

## State and secrets

Terraform's state file (`terraform.tfstate`) holds the SDK keys and the trigger URL in plain text. It is git-ignored; keep it private. A team would keep state in an encrypted remote backend with locking, such as an S3 bucket or HCP Terraform. If the file is lost, adopt the project again as above.

## Remove it

The project resource has `prevent_destroy`, because deleting a project deletes every flag, metric and SDK key in it. To remove a trial project, delete it in LaunchDarkly (**Project settings > Delete project**), then delete the state file.

## Tests

```bash
terraform init -backend=false && terraform test
```

`tests/plan.tftest.hcl` runs plan-only checks against a mocked provider, so it needs no account or token. It checks that the release flag starts off and serves `false` to everyone but ABC Freight's own staff, that the assistant metrics treat lower as better, that the booking metric waits for the experiments checkbox, and that the trigger is optional. CI runs `terraform fmt`, `validate` and `test` on every push, and `tests/test_terraform.py` checks that the keys here match the app's.
