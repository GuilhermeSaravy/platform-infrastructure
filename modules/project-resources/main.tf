locals {
  defaults    = yamldecode(file("${var.repository_root}/organization/defaults.yaml"))
  naming      = yamldecode(file("${var.repository_root}/organization/naming.yaml"))
  project     = yamldecode(file("${var.repository_root}/projects/${var.project_name}/project.yaml"))
  runtimes    = { for capability in local.project.capabilities : capability.name => capability if capability.type == "application-runtime" }
  storage     = { for capability in local.project.capabilities : capability.name => capability if capability.type == "object-storage" }
  containers  = { for pair in flatten([for name, capability in local.storage : [for container in capability.azure.containers : { capability = name, container = container }]]) : "${pair.capability}/${pair.container}" => pair }
  network_rg  = format(local.naming.network_resource_group, var.environment)
  network     = format(local.naming.virtual_network, var.environment)
  storage_name = format(local.naming.storage, var.project_name, var.environment, var.unique_suffix)
  tags = merge(var.common_tags, {
    owner       = local.project.owner.team
    project     = var.project_name
    environment = var.environment
    cost_center = local.project.cost_center
  })
}
resource "azurerm_resource_group" "project" {
  name     = format(local.naming.resource_group, var.project_name, var.environment)
  location = var.location
  tags     = local.tags
  lifecycle {
    precondition {
      condition     = local.project.name == var.project_name && contains(local.project.environments, var.environment)
      error_message = "The project name must match its folder and declare this environment."
    }
    precondition {
      condition     = contains(keys(local.defaults.teams), local.project.owner.team) && contains(local.defaults.azure.allowed_locations, var.location)
      error_message = "Use a declared owner team and approved location."
    }
    precondition {
      condition     = length(local.runtimes) <= 1 && length(local.storage) <= 1 && alltrue([for capability in local.project.capabilities : contains(["application-runtime", "object-storage"], capability.type)])
      error_message = "Supported project capabilities are at most one application-runtime and one object-storage."
    }
    precondition {
      condition     = length(local.storage) == 0 || length(local.storage_name) <= 24
      error_message = "Storage naming exceeds Azure's 24-character limit; shorten project name or unique suffix."
    }
  }
}
data "azurerm_subnet" "integration" {
  name                 = format(local.naming.integration_subnet, var.project_name)
  virtual_network_name = local.network
  resource_group_name  = local.network_rg
}
data "azurerm_subnet" "private_endpoints" {
  name                 = local.naming.private_endpoint_subnet
  virtual_network_name = local.network
  resource_group_name  = local.network_rg
}
data "azurerm_private_dns_zone" "services" {
  for_each            = { blob = "privatelink.blob.core.windows.net", web = "privatelink.azurewebsites.net" }
  name                = each.value
  resource_group_name = local.network_rg
}
resource "azurerm_user_assigned_identity" "runtime" {
  for_each            = local.runtimes
  name                = format(local.naming.workload_identity, var.project_name, var.environment, each.key)
  resource_group_name = azurerm_resource_group.project.name
  location            = azurerm_resource_group.project.location
  tags                = local.tags
}
resource "azurerm_service_plan" "runtime" {
  for_each            = local.runtimes
  name                = format(local.naming.service_plan, var.project_name, var.environment)
  resource_group_name = azurerm_resource_group.project.name
  location            = azurerm_resource_group.project.location
  os_type             = "Linux"
  sku_name            = each.value.azure.sku
  tags                = local.tags
}
resource "azurerm_linux_web_app" "runtime" {
  for_each                      = local.runtimes
  name                          = format(local.naming.runtime, var.project_name, var.environment, var.unique_suffix)
  resource_group_name           = azurerm_resource_group.project.name
  location                      = azurerm_resource_group.project.location
  service_plan_id               = azurerm_service_plan.runtime[each.key].id
  virtual_network_subnet_id      = data.azurerm_subnet.integration.id
  public_network_access_enabled = false
  https_only                    = true
  tags                          = local.tags
  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.runtime[each.key].id]
  }
  site_config {
    always_on              = true
    ftps_state             = "Disabled"
    minimum_tls_version    = "1.2"
    vnet_route_all_enabled = false
    health_check_path      = "/health"
    application_stack {
      docker_image_name   = trimprefix(var.demo_image, "ghcr.io/")
      docker_registry_url = "https://ghcr.io"
    }
  }
  app_settings = {
    WEBSITES_PORT              = tostring(each.value.azure.port)
    WEBSITES_ENABLE_APP_SERVICE_STORAGE = "false"
    AZURE_WORKLOAD_CLIENT_ID   = azurerm_user_assigned_identity.runtime[each.key].client_id
    ENABLE_PROBES              = var.project_name == "catalog" && var.environment == "dev" ? "true" : "false"
    ORDERS_STORAGE_ACCOUNT     = format(local.naming.storage, "orders", var.environment, var.unique_suffix)
  }
}
resource "azurerm_storage_account" "capability" {
  for_each                        = local.storage
  name                            = local.storage_name
  resource_group_name             = azurerm_resource_group.project.name
  location                        = azurerm_resource_group.project.location
  account_kind                    = "StorageV2"
  account_tier                    = each.value.azure.account_tier
  account_replication_type        = each.value.azure.replication_type
  min_tls_version                 = "TLS1_2"
  https_traffic_only_enabled      = true
  public_network_access_enabled  = false
  shared_access_key_enabled      = false
  allow_nested_items_to_be_public = false
  default_to_oauth_authentication = true
  tags                            = local.tags
  blob_properties {
    versioning_enabled = true
    delete_retention_policy {
      days = 7
    }
  }
}
resource "azurerm_storage_container" "capability" {
  for_each              = local.containers
  name                  = each.value.container
  storage_account_id    = azurerm_storage_account.capability[each.value.capability].id
  container_access_type = "private"
}
resource "azurerm_private_endpoint" "runtime" {
  for_each            = local.runtimes
  name                = "pe-${var.project_name}-${var.environment}-${each.key}"
  resource_group_name = azurerm_resource_group.project.name
  location            = azurerm_resource_group.project.location
  subnet_id           = data.azurerm_subnet.private_endpoints.id
  tags                = local.tags
  private_service_connection {
    name                           = "runtime"
    private_connection_resource_id = azurerm_linux_web_app.runtime[each.key].id
    subresource_names              = ["sites"]
    is_manual_connection           = false
  }
  private_dns_zone_group {
    name                 = "web"
    private_dns_zone_ids = [data.azurerm_private_dns_zone.services["web"].id]
  }
}
resource "azurerm_private_endpoint" "storage" {
  for_each            = local.storage
  name                = "pe-${var.project_name}-${var.environment}-${each.key}"
  resource_group_name = azurerm_resource_group.project.name
  location            = azurerm_resource_group.project.location
  subnet_id           = data.azurerm_subnet.private_endpoints.id
  tags                = local.tags
  private_service_connection {
    name                           = "blob"
    private_connection_resource_id = azurerm_storage_account.capability[each.key].id
    subresource_names              = ["blob"]
    is_manual_connection           = false
  }
  private_dns_zone_group {
    name                 = "blob"
    private_dns_zone_ids = [data.azurerm_private_dns_zone.services["blob"].id]
  }
}
