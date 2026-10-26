# 6. LaunchDarkly configuration as code, with targeting left to LaunchDarkly

**Status:** accepted

## Context

Every LaunchDarkly object was first created by hand from the setup guide, and two hand mistakes showed up: `eta-predictions` was created with its default rule serving `true`, and the output-token metric was left at "higher is better" ([AI_EXPERIMENT.md](../AI_EXPERIMENT.md)). A customer repeating the setup can make the same ones.

LaunchDarkly's Terraform provider can manage most of the setup. It cannot manage experiments, AI Config targeting, or the "available for experiments" setting of a context kind. LaunchDarkly also advises against managing targeting with Terraform: an apply can undo changes made in the UI and break a running experiment.

## Decision

`terraform/` manages the definitions: the project and its environments, the `organization` context kind, both flags, the trigger, the metrics, and the AI Config with its variations. It creates each flag's starting targeting in Test and then ignores it (`lifecycle { ignore_changes = all }`), so releases, rollbacks and experiments stay in LaunchDarkly. Everything Terraform manages carries the tag `managed-by-terraform`.

The demo project, first built by hand, was adopted with `import` rather than rebuilt, which kept its SDK keys, trigger URL, Slack subscription and experiment results. `terraform plan` reports no changes.

## Consequences

- A customer gets the setup from `terraform apply`, one checkbox and a second apply. `terraform/README.md` lists the remaining manual steps.
- The two mistakes cannot come back: the metric direction and the release flag's starting targeting are code, and `terraform/tests` checks both.
- A later apply never undoes a release, a trigger rollback or a running experiment. The trade-off: editing targeting in code has no effect after the first apply.
- Terraform's state holds the SDK keys and the trigger URL in plain text. It is git-ignored here; a team would use an encrypted remote backend.
- A new project needs an Admin token, because the Writer role cannot create context kinds.
- The provider accepts an inline model or a model config for an AI Config variation, not both, and only the inline model carries `max_tokens`. Variations name the model ID directly.
- Not done: custom roles that stop people editing Terraform-managed fields in the UI, which LaunchDarkly recommends for production.
- Rejected: managing targeting with Terraform (it would undo rollbacks and break experiments), and deploying the app with Terraform (this is a sample the customer runs locally).
