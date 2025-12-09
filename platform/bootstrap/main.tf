data "azurerm_client_config" "operator" {}

locals {
  subscription_scope = "/subscriptions/${data.azurerm_client_config.operator.subscription_id}"
  tags = {
    organization = "northstar"
    owner        = "platform-engineering"
    project      = "platform-state"
    environment  = "shared"
    cost_center  = "commerce-platform"
    managed_by   = "terraform"
  }
  deployment_roles = toset([
    "Contributor",
    "User Access Administrator",
    "Resource Policy Contributor"
  ])
}

resource "azurerm_resource_group" "state" {
  name     = "rg-platform-state"
  location = var.location
  tags     = local.tags
  lifecycle {
    prevent_destroy = true
  }
}

resource "azurerm_storage_account" "state" {
  name                            = "stnorthstartf${var.unique_suffix}"
  resource_group_name             = azurerm_resource_group.state.name
  location                        = azurerm_resource_group.state.location
  account_kind                    = "StorageV2"
  account_tier                    = "Standard"
  account_replication_type        = "LRS"
  min_tls_version                 = "TLS1_2"
  https_traffic_only_enabled       = true
  public_network_access_enabled   = true
  shared_access_key_enabled       = false
  allow_nested_items_to_be_public = false
  default_to_oauth_authentication = true
  tags                            = local.tags

  blob_properties {
    versioning_enabled = true
    delete_retention_policy {
      days = 14
    }
    container_delete_retention_policy {
      days = 14
    }
  }

  lifecycle {
    prevent_destroy = true
  }
}

resource "azurerm_storage_container" "state" {
  name                  = "tfstate"
  storage_account_id    = azurerm_storage_account.state.id
  container_access_type = "private"
  lifecycle {
    prevent_destroy = true
  }
}

resource "azurerm_user_assigned_identity" "deployment" {
  name                = "id-platform-deployment"
  location            = azurerm_resource_group.state.location
  resource_group_name = azurerm_resource_group.state.name
  tags                = local.tags
}

resource "azurerm_federated_identity_credential" "github" {
  name                = "github-platform-environment"
  resource_group_name = azurerm_resource_group.state.name
  parent_id           = azurerm_user_assigned_identity.deployment.id
  audience            = ["api://AzureADTokenExchange"]
  issuer              = "https://token.actions.githubusercontent.com"
  subject             = "repo:${var.github_repository}:environment:platform"
}

resource "azurerm_role_assignment" "deployment_management" {
  for_each                         = local.deployment_roles
  scope                            = local.subscription_scope
  role_definition_name             = each.value
  principal_id                     = azurerm_user_assigned_identity.deployment.principal_id
  principal_type                   = "ServicePrincipal"
  skip_service_principal_aad_check = true
}

resource "azurerm_role_assignment" "deployment_state" {
  scope                            = azurerm_storage_container.state.resource_manager_id
  role_definition_name             = "Storage Blob Data Contributor"
  principal_id                     = azurerm_user_assigned_identity.deployment.principal_id
  principal_type                   = "ServicePrincipal"
  skip_service_principal_aad_check = true
}

resource "azurerm_role_assignment" "operator_state" {
  scope                = azurerm_storage_container.state.resource_manager_id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = var.bootstrap_operator_object_id
  principal_type       = "User"
}
