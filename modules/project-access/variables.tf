variable "repository_root" {
  type        = string
  description = "Absolute checkout path containing the organization and project contracts."
}
variable "environment" {
  type = string
  validation {
    condition     = contains(["dev", "prod"], var.environment)
    error_message = "Choose dev or prod."
  }
}
variable "project_name" {
  type = string
  validation {
    condition     = can(regex("^[a-z][a-z0-9]{2,9}$", var.project_name))
    error_message = "Project names must be 3-10 lowercase alphanumeric characters, starting with a letter."
  }
}
variable "unique_suffix" {
  type = string
  validation {
    condition     = can(regex("^[a-z0-9]{6,10}$", var.unique_suffix))
    error_message = "PLATFORM_UNIQUE_SUFFIX must be 6-10 lowercase letters or digits."
  }
}
variable "location" {
  type = string
}
variable "common_tags" {
  type = map(string)
}

variable "team_group_ids" {
  type        = map(string)
  sensitive   = true
  description = "External logical-team mappings consumed only by the identity resolution module."
}
