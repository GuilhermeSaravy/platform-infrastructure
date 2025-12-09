variable "unique_suffix" {
  type        = string
  description = "Globally unique editable lowercase alphanumeric suffix, 6-10 characters, shared with normal execution."
  validation {
    condition     = can(regex("^[a-z0-9]{6,10}$", var.unique_suffix))
    error_message = "unique_suffix must be 6-10 lowercase letters or digits. Select your own unique suffix before bootstrap."
  }
}

variable "github_repository" {
  type        = string
  description = "Actual GitHub owner/repository for the platform environment OIDC trust."
  validation {
    condition     = can(regex("^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$", var.github_repository)) && !can(regex("(?i)(placeholder|example|your[-_])", var.github_repository))
    error_message = "github_repository must be your real owner/repository, without a URL or placeholder."
  }
}

variable "bootstrap_operator_object_id" {
  type        = string
  sensitive   = true
  description = "Entra user object ID of the interactive bootstrap operator, for state-container data access."
  validation {
    condition     = can(regex("^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$", var.bootstrap_operator_object_id)) && var.bootstrap_operator_object_id != "00000000-0000-0000-0000-000000000000"
    error_message = "Supply the existing interactive user's Entra object ID through TF_VAR_bootstrap_operator_object_id."
  }
}

variable "location" {
  type        = string
  default     = "westeurope"
  description = "Editable historically supported Azure region for bootstrap resources."
}
