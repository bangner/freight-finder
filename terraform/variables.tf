variable "project_key" {
  description = "Key of the LaunchDarkly project. If you change it, set LD_PROJECT_KEY in the app's .env to match."
  type        = string
  default     = "abc-freight"
}

variable "project_name" {
  description = "Display name of the LaunchDarkly project."
  type        = string
  default     = "ABC Freight"
}

variable "create_trigger" {
  description = "Create the flag trigger that turns eta-predictions off (Part 1 remediation). Flag triggers need an Enterprise plan; without one, set this to false and use the REST fallback in scripts/rollback.sh."
  type        = bool
  default     = true
}

variable "create_booking_metric" {
  description = "Create the booking metric for the hours-of-service experiment. It measures organizations, which LaunchDarkly allows only after the organization context kind is marked \"Available for experiments\", a setting Terraform cannot change. Tick it in LaunchDarkly, then apply again with this set to true."
  type        = bool
  default     = false
}
