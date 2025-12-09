locals {
  repository_root = get_repo_root()
  defaults        = yamldecode(file("${local.repository_root}/organization/defaults.yaml"))
  suffix          = get_env("PLATFORM_UNIQUE_SUFFIX")
}
terraform_version_constraint  = "= 1.10.5"
terragrunt_version_constraint = "= 0.77.22"

generate "provider" {
  path      = "provider.generated.tf"
  if_exists = "overwrite_terragrunt"
  contents  = <<-EOT
    terraform {
      required_version = "= 1.10.5"
      required_providers {
        azurerm = {
          source  = "hashicorp/azurerm"
          version = "= 4.27.0"
        }
      }
    }
    provider "azurerm" {
      features {}
      resource_provider_registrations = "none"
      storage_use_azuread             = true
    }
  EOT
}
generate "provider_lock" {
  path              = ".terraform.lock.hcl"
  if_exists         = "overwrite"
  disable_signature = true
  contents          = file("${local.repository_root}/.terraform.lock.hcl")
}
remote_state {
  backend = "azurerm"
  generate = {
    path      = "backend.generated.tf"
    if_exists = "overwrite_terragrunt"
  }
  config = {
    resource_group_name  = "rg-platform-state"
    storage_account_name = "stnorthstartf${local.suffix}"
    container_name       = "tfstate"
    key                  = "${path_relative_to_include()}/terraform.tfstate"
    use_azuread_auth     = true
    use_oidc             = get_env("ARM_USE_OIDC", "false") == "true"
  }
}
inputs = {
  repository_root = local.repository_root
  unique_suffix   = local.suffix
  location        = local.defaults.azure.location
  team_group_ids  = jsondecode(get_env("AZURE_TEAM_GROUP_IDS", "{}"))
  demo_image      = get_env("DEMO_IMAGE", "")
  common_tags = merge(local.defaults.tags, {
    owner       = "platform-engineering"
    project     = "platform"
    environment = "shared"
    cost_center = local.defaults.cost_center
  })
}
