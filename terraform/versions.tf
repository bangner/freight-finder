terraform {
  # 1.7 or newer: the tests in tests/ use mock_provider.
  required_version = ">= 1.7"

  required_providers {
    launchdarkly = {
      source  = "launchdarkly/launchdarkly"
      version = "~> 3.1"
    }
  }
}

# Reads the access token from LAUNCHDARKLY_ACCESS_TOKEN. Never put it in a .tf
# or .tfvars file.
provider "launchdarkly" {
  # Removing a flag from this code archives it in LaunchDarkly instead of
  # deleting it, so it can be restored (docs/RUNBOOK.md, "Retire a release flag").
  archive_flags_on_destroy = true
}
