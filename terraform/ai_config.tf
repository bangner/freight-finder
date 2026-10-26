# Extra credit: the dispatcher assistant's models and prompts. Who gets which
# variation (enterprise customers get friendly, everyone else concise) is set
# in LaunchDarkly: the provider has no resource for AI Config targeting
# (docs/LAUNCHDARKLY_SETUP.md, step 7).
resource "launchdarkly_ai_config" "dispatcher_assistant" {
  project_key = launchdarkly_project.abc_freight.key
  key         = "dispatcher-assistant" # must match ASSISTANT_CONFIG in app/flags.py
  name        = "Dispatcher Assistant"
  mode        = "completion"
  tags        = local.tags
}

# modelName is the Anthropic model ID the app calls. The LaunchDarkly UI also
# links a built-in model config, but the provider accepts an inline model or a
# model config, not both, and only the inline model carries max_tokens.
# max_tokens looks high for short answers, but current models think before
# answering and thinking counts toward it. The app fills in {{ shipper_name }}
# and {{ loads }} (app/assistant.py).
resource "launchdarkly_ai_config_variation" "concise" {
  project_key = launchdarkly_project.abc_freight.key
  config_key  = launchdarkly_ai_config.dispatcher_assistant.key
  key         = "concise"
  name        = "concise"
  model = jsonencode({
    modelName  = "claude-haiku-5-5"
    parameters = { max_tokens = 2000 }
  })

  messages = [
    {
      role = "system"
      content = chomp(<<-EOT
        You are the dispatcher assistant for {{ shipper_name }}. Answer in at most two sentences, using only these loads:
        {{ loads }}

        Reply in plain text, without Markdown.
      EOT
      )
    },
  ]
}

resource "launchdarkly_ai_config_variation" "friendly" {
  project_key = launchdarkly_project.abc_freight.key
  config_key  = launchdarkly_ai_config.dispatcher_assistant.key
  key         = "friendly"
  name        = "friendly"
  model = jsonencode({
    modelName  = "claude-sonnet-5-5"
    parameters = { max_tokens = 4000 }
  })

  messages = [
    {
      role = "system"
      content = chomp(<<-EOT
        You are a friendly dispatcher assistant for {{ shipper_name }}. Explain your answer briefly and suggest a next step. Use only these loads:
        {{ loads }}

        Reply in plain text, without Markdown.
      EOT
      )
    },
  ]
}
