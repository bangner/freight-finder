locals {
  # On every object Terraform manages, so people can see in LaunchDarkly which
  # objects to change in code rather than by hand.
  tags = ["managed-by-terraform"]
}

resource "launchdarkly_project" "abc_freight" {
  key  = var.project_key
  name = var.project_name
  tags = local.tags

  # The app uses Test. This map is the project's complete list of environments:
  # an environment missing from it is deleted on apply, SDK keys included.
  environments = {
    test = {
      name  = "Test"
      color = "EBFF38"
    }
    # Every change in Production needs a comment and a confirmation.
    production = {
      name             = "Production"
      color            = "00DA7B"
      critical         = true
      require_comments = true
      confirm_changes  = true
    }
  }

  lifecycle {
    # Deleting the project deletes every flag, metric and SDK key in it. To tear
    # down a trial on purpose, delete the project in LaunchDarkly instead.
    prevent_destroy = true
  }
}

# The app evaluates every flag with a user and an organization in one
# multi-context (app/contexts.py).
resource "launchdarkly_context_kind" "organization" {
  project_key = launchdarkly_project.abc_freight.key
  key         = "organization"
  name        = "organization"
}
