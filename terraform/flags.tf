# Terraform owns each flag's definition: its variations, description and
# lifecycle. It only creates the starting targeting in Test; after that,
# targeting belongs to LaunchDarkly (lifecycle ignore_changes below), so a later
# apply never undoes a release, a trigger rollback or a running experiment.
# docs/decisions/0006-launchdarkly-configuration-as-code.md explains the split.

# Part 1: the Live ETA panel. A temporary release flag, removed once the panel
# is fully released (docs/RUNBOOK.md, "Retire a release flag").
resource "launchdarkly_feature_flag" "eta_predictions" {
  project_key    = launchdarkly_project.abc_freight.key
  key            = "eta-predictions" # must match ETA_FLAG in app/flags.py
  name           = "ETA predictions"
  description    = "Display ETA predictions in the UI"
  variation_type = "boolean"
  temporary      = true
  tags           = local.tags

  variations = [
    { value = "true", name = "true" },
    { value = "false", name = "false" },
  ]

  # In environments created later, such as Production, the flag serves false
  # whether it is on or off, so turning it on there releases nothing by itself.
  defaults = {
    on_variation  = 1
    off_variation = 1
  }
}

# Starts off. Turning it on releases to ABC Freight's own staff (Quinn) and
# nobody else; changing the default rule to true releases to every customer.
resource "launchdarkly_feature_flag_environment" "eta_predictions_test" {
  flag_id = launchdarkly_feature_flag.eta_predictions.id
  env_key = "test"

  on            = false
  off_variation = 1
  fallthrough   = { variation = 1 }

  context_targets = [
    { context_kind = "organization", values = ["abc-freight"], variation = 0 },
  ]

  lifecycle {
    ignore_changes = all
  }

  depends_on = [launchdarkly_context_kind.organization]
}

# Part 1 remediation: a secret URL whose only action is turning eta-predictions
# off in Test (scripts/rollback.sh). Flag triggers need an Enterprise plan.
resource "launchdarkly_flag_trigger" "eta_predictions_off" {
  count = var.create_trigger ? 1 : 0

  project_key     = launchdarkly_project.abc_freight.key
  env_key         = "test"
  flag_key        = launchdarkly_feature_flag.eta_predictions.key
  integration_key = "generic-trigger"
  instructions    = { kind = "turnFlagOff" }
  enabled         = true
}

# Part 2: which country's hours-of-service rules an organization sees, if any.
# Long-lived: it encodes a business rule, not a release.
resource "launchdarkly_feature_flag" "driver_hours_of_service" {
  project_key    = launchdarkly_project.abc_freight.key
  key            = "driver-hours-of-service" # must match HOS_FLAG in app/flags.py
  name           = "Driver hours of service"
  description    = "Display HOS for Drivers"
  variation_type = "string"
  temporary      = false
  tags           = local.tags

  variations = [
    { value = "off", name = "off" },
    { value = "us", name = "us" },
    { value = "canada", name = "canada" },
  ]

  defaults = {
    on_variation  = 0
    off_variation = 0
  }
}

# On, serving "off" by default. Lakeshore Logistics (Riley) is an individual
# target; two rules serve enterprise customers by region. The footer and
# scripts/explain.py name the rules by position, so keep this order.
resource "launchdarkly_feature_flag_environment" "driver_hours_of_service_test" {
  flag_id = launchdarkly_feature_flag.driver_hours_of_service.id
  env_key = "test"

  on            = true
  off_variation = 0
  fallthrough   = { variation = 0 }

  context_targets = [
    { context_kind = "organization", values = ["lakeshore-logistics"], variation = 1 },
  ]

  rules = [
    {
      description = "Enterprise in US"
      clauses = [
        { context_kind = "organization", attribute = "plan", op = "in", values = ["enterprise"] },
        { context_kind = "organization", attribute = "region", op = "in", values = ["US"] },
      ]
      variation = 1
    },
    {
      description = "Enterprise in Canada"
      clauses = [
        { context_kind = "organization", attribute = "plan", op = "in", values = ["enterprise"] },
        { context_kind = "organization", attribute = "region", op = "in", values = ["CA"] },
      ]
      variation = 2
    },
  ]

  lifecycle {
    ignore_changes = all
  }

  depends_on = [launchdarkly_context_kind.organization]
}
