# Plan-only checks against a mocked provider: no LaunchDarkly account or token.
# Run from terraform/ with: terraform test

mock_provider "launchdarkly" {}

run "release_flag_starts_safe" {
  command = plan

  assert {
    condition     = launchdarkly_feature_flag_environment.eta_predictions_test.on == false
    error_message = "eta-predictions must start off."
  }

  assert {
    condition     = launchdarkly_feature_flag.eta_predictions.variations[launchdarkly_feature_flag_environment.eta_predictions_test.fallthrough.variation].value == "false"
    error_message = "Turned on, eta-predictions must serve false to everyone it does not target."
  }

  assert {
    condition = anytrue([
      for target in launchdarkly_feature_flag_environment.eta_predictions_test.context_targets :
      target.context_kind == "organization" && contains(target.values, "abc-freight")
      && launchdarkly_feature_flag.eta_predictions.variations[target.variation].value == "true"
    ])
    error_message = "ABC Freight's own staff must see the panel before any customer."
  }
}

run "assistant_metrics_reward_lower_values" {
  command = plan

  assert {
    condition = alltrue([
      for metric in [launchdarkly_metric.assistant_response_time, launchdarkly_metric.assistant_output_tokens] :
      metric.success_criteria == "LowerThanBaseline" && !metric.include_units_without_events
    ])
    error_message = "A faster, shorter answer is the better one, and a visitor who asked nothing must not count as 0."
  }
}

run "booking_metric_waits_for_the_experiments_checkbox" {
  command = plan

  # The default, set explicitly so a local terraform.tfvars cannot change it.
  variables {
    create_booking_metric = false
  }

  assert {
    condition     = length(launchdarkly_metric.book_load_clicked) == 0
    error_message = "The booking metric needs the organization kind to be available for experiments first."
  }
}

run "booking_metric_measures_organizations" {
  command = plan

  variables {
    create_booking_metric = true
  }

  assert {
    condition     = contains(launchdarkly_metric.book_load_clicked[0].analysis_units, "organization")
    error_message = "The experiment randomizes by organization, so its metric must measure organizations."
  }
}

run "trigger_is_optional" {
  command = plan

  variables {
    create_trigger = false
  }

  assert {
    condition     = length(launchdarkly_flag_trigger.eta_predictions_off) == 0
    error_message = "Without an Enterprise plan there is no trigger to create."
  }
}
