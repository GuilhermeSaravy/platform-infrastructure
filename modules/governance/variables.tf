variable "repository_root" {
  type        = string
  description = "Absolute checkout containing organization policies and discovered project declarations."
}

variable "environment" {
  type        = string
  description = "Environment whose existing platform and project resource groups receive policy assignments."
  validation {
    condition     = contains(["dev", "prod"], var.environment)
    error_message = "environment must be dev or prod."
  }
}

variable "unique_suffix" {
  type        = string
  description = "Deployment suffix accepted by the common interface; policies use subscription-scoped environment names."
}

variable "location" {
  type        = string
  description = "Approved platform region; deny-only assignments do not require an identity or location."
}

variable "common_tags" {
  type        = map(string)
  description = "Organization tags accepted by the common interface; policies use metadata rather than resource tags."
}
