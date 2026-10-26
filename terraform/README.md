# Terraform

The LaunchDarkly setup for ABC Freight as code. How to run it, what it creates and what stays manual: [docs/SETUP.md](../docs/SETUP.md#a-terraform).

- `tests/plan.tftest.hcl`: plan-only checks against a mocked provider. Run `terraform init -backend=false && terraform test`.
- `imports.tf.example`: adopts a project that was set up by hand.
