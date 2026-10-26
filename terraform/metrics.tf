# Hours-of-service experiment (docs/EXPERIMENTS.md): did the organization book a
# load at least once. Created only once the organization context kind is
# available for experiments (see var.create_booking_metric).
resource "launchdarkly_metric" "book_load_clicked" {
  count = var.create_booking_metric ? 1 : 0

  project_key                  = launchdarkly_project.abc_freight.key
  key                          = "book-a-load-clicked"
  name                         = "Book a load clicked"
  kind                         = "custom"
  event_key                    = "book-load-clicked" # sent by POST /api/track (app/main.py)
  is_numeric                   = false
  success_criteria             = "HigherThanBaseline"
  include_units_without_events = true # an organization that never booked counts as not converted
  analysis_units               = [launchdarkly_context_kind.organization.key]
  tags                         = local.tags
}

# AI Config experiment (docs/EXPERIMENTS.md). The AI SDK sends both events for
# every answer (app/assistant.py). For both, lower is better: left at the
# default, LaunchDarkly would score a slower or longer answer as an improvement.
resource "launchdarkly_metric" "assistant_response_time" {
  project_key                  = launchdarkly_project.abc_freight.key
  key                          = "assistant-response-time"
  name                         = "Assistant response time"
  kind                         = "custom"
  event_key                    = "$ld:ai:duration:total"
  is_numeric                   = true
  unit                         = "ms"
  success_criteria             = "LowerThanBaseline"
  analysis_type                = "mean"
  unit_aggregation_type        = "average"
  include_units_without_events = false # a visitor who asked nothing is not a 0 ms answer
  analysis_units               = ["user"]
  tags                         = local.tags
}

resource "launchdarkly_metric" "assistant_output_tokens" {
  project_key                  = launchdarkly_project.abc_freight.key
  key                          = "assistant-output-tokens"
  name                         = "Assistant output tokens"
  kind                         = "custom"
  event_key                    = "$ld:ai:tokens:output"
  is_numeric                   = true
  unit                         = "tokens"
  success_criteria             = "LowerThanBaseline"
  analysis_type                = "mean"
  unit_aggregation_type        = "average"
  include_units_without_events = false
  analysis_units               = ["user"]
  tags                         = local.tags
}
