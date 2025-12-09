variable "repository_root" {
  type        = string
  description = "Absolute checkout path containing organization and project declarations."
}

variable "environment" {
  type        = string
  description = "Environment with its own shared network and state."
  validation {
    condition     = contains(["dev", "prod"], var.environment)
    error_message = "environment must be dev or prod."
  }
}

variable "unique_suffix" {
  type        = string
  description = "Deployment suffix accepted by the common module interface. Network names are environment scoped."
}

variable "location" {
  type        = string
  description = "Azure region shared by the VNet and integrated App Service plans."
}

variable "common_tags" {
  type        = map(string)
  description = "Organization tags; platform ownership tags are added by this module."
}
