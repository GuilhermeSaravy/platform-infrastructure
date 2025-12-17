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

variable "demo_image" {
  type        = string
  description = "Public GHCR image reference containing an immutable sha256 digest; linux/amd64."
  validation {
    condition     = can(regex("^ghcr[.]io/[a-z0-9][a-z0-9._/-]*@sha256:[0-9a-f]{64}$", var.demo_image))
    error_message = "Set DEMO_IMAGE to a public ghcr.io/owner/image@sha256:<64 lowercase hex> image."
  }
}
