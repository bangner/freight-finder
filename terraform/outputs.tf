# Both values are secrets. Copy them into the app's .env without printing them:
#   terraform output -raw sdk_key
#   terraform output -raw trigger_url
# Terraform also keeps them in plain text in its state file, which is git-ignored.

output "sdk_key" {
  description = "Server-side SDK key for the Test environment: LAUNCHDARKLY_SDK_KEY in .env."
  value       = launchdarkly_project.abc_freight.environments["test"].api_key
  sensitive   = true
}

output "trigger_url" {
  description = "URL of the trigger that turns eta-predictions off: LD_TRIGGER_URL in .env. Null without a trigger."
  value       = one(launchdarkly_flag_trigger.eta_predictions_off[*].trigger_url)
  sensitive   = true
}

output "manual_steps" {
  description = "What Terraform cannot set up."
  value       = <<-EOT
    Finish in LaunchDarkly (terraform/README.md has the details):
    1. AI Config dispatcher-assistant: turn targeting on in Test, serve concise by default,
       and add a rule serving friendly when organization plan is enterprise.
    2. For the experiments: mark the organization context kind "Available for experiments",
       then apply again with -var create_booking_metric=true.
    3. Optional: the two experiments (docs/LAUNCHDARKLY_SETUP.md, steps 6 and 7) and Slack (step 8).
  EOT
}
