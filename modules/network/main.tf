locals {
  naming   = yamldecode(file("${var.repository_root}/organization/naming.yaml"))
  defaults = yamldecode(file("${var.repository_root}/organization/defaults.yaml"))
  declarations = [
    for path in fileset(var.repository_root, "projects/*/project.yaml") :
    yamldecode(file("${var.repository_root}/${path}"))
  ]
  projects = {
    for project in local.declarations : project.name => project
    if contains(project.environments, var.environment)
  }
  network_cidr          = local.defaults.azure.network_cidrs[var.environment]
  private_endpoint_cidr = cidrsubnet(local.network_cidr, 8, 1)
  operator_cidr         = cidrsubnet(local.network_cidr, 8, 2)
  integration_cidrs = {
    for name, project in local.projects : name => cidrsubnet(local.network_cidr, 10, 64 + project.azure.network_slot)
  }
  tags = merge(var.common_tags, {
    owner       = "platform-engineering"
    project     = "platform-network"
    environment = var.environment
  })
  dns_zones = {
    blob = "privatelink.blob.core.windows.net"
    web  = "privatelink.azurewebsites.net"
  }
}

resource "azurerm_resource_group" "network" {
  name     = format(local.naming.network_resource_group, var.environment)
  location = var.location
  tags     = local.tags

  lifecycle {
    precondition {
      condition     = contains(local.defaults.azure.allowed_locations, var.location)
      error_message = "Select an organization-approved Azure region."
    }
    precondition {
      condition     = length(distinct([for project in values(local.projects) : project.azure.network_slot])) == length(local.projects)
      error_message = "Each project must have a unique azure.network_slot; retain existing slots when onboarding."
    }
    precondition {
      condition     = alltrue([for project in values(local.projects) : project.azure.network_slot >= 0 && project.azure.network_slot <= 127 && floor(project.azure.network_slot) == project.azure.network_slot])
      error_message = "azure.network_slot must be an integer between 0 and 127."
    }
  }
}

resource "azurerm_virtual_network" "shared" {
  name                = format(local.naming.virtual_network, var.environment)
  location            = azurerm_resource_group.network.location
  resource_group_name = azurerm_resource_group.network.name
  address_space       = [local.network_cidr]
  tags                = local.tags
}

resource "azurerm_subnet" "integration" {
  for_each             = local.projects
  name                 = format(local.naming.integration_subnet, each.key)
  resource_group_name  = azurerm_resource_group.network.name
  virtual_network_name = azurerm_virtual_network.shared.name
  address_prefixes     = [local.integration_cidrs[each.key]]

  delegation {
    name = "app-service"
    service_delegation {
      name    = "Microsoft.Web/serverFarms"
      actions = ["Microsoft.Network/virtualNetworks/subnets/action"]
    }
  }
}

resource "azurerm_subnet" "private_endpoints" {
  name                              = local.naming.private_endpoint_subnet
  resource_group_name               = azurerm_resource_group.network.name
  virtual_network_name              = azurerm_virtual_network.shared.name
  address_prefixes                  = [local.private_endpoint_cidr]
  private_endpoint_network_policies = "Enabled"
}

resource "azurerm_subnet" "operators" {
  name                 = local.naming.operator_subnet
  resource_group_name  = azurerm_resource_group.network.name
  virtual_network_name = azurerm_virtual_network.shared.name
  address_prefixes     = [local.operator_cidr]
}

resource "azurerm_network_security_group" "integration" {
  for_each            = local.projects
  name                = "nsg-${each.key}-app-${var.environment}"
  location            = azurerm_resource_group.network.location
  resource_group_name = azurerm_resource_group.network.name
  tags                = local.tags

  security_rule {
    name                       = "allow-private-service-https"
    priority                   = 100
    direction                  = "Outbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "443"
    source_address_prefix      = local.integration_cidrs[each.key]
    destination_address_prefix = local.private_endpoint_cidr
  }
  security_rule {
    name                       = "allow-platform-dns"
    priority                   = 110
    direction                  = "Outbound"
    access                     = "Allow"
    protocol                   = "*"
    source_port_range          = "*"
    destination_port_range     = "53"
    source_address_prefix      = local.integration_cidrs[each.key]
    destination_address_prefix = "AzurePlatformDNS"
  }
  security_rule {
    name                       = "deny-other-private-connectivity"
    priority                   = 200
    direction                  = "Outbound"
    access                     = "Deny"
    protocol                   = "*"
    source_port_range          = "*"
    destination_port_range     = "*"
    source_address_prefix      = "*"
    destination_address_prefix = "VirtualNetwork"
  }
}

resource "azurerm_network_security_group" "private_endpoints" {
  name                = "nsg-private-endpoints-${var.environment}"
  location            = azurerm_resource_group.network.location
  resource_group_name = azurerm_resource_group.network.name
  tags                = local.tags

  security_rule {
    name                       = "allow-runtime-and-operator-https"
    priority                   = 100
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "443"
    source_address_prefixes    = concat(values(local.integration_cidrs), [local.operator_cidr])
    destination_address_prefix = local.private_endpoint_cidr
  }
  security_rule {
    name                       = "deny-other-private-inbound"
    priority                   = 200
    direction                  = "Inbound"
    access                     = "Deny"
    protocol                   = "*"
    source_port_range          = "*"
    destination_port_range     = "*"
    source_address_prefix      = "VirtualNetwork"
    destination_address_prefix = "*"
  }
}

resource "azurerm_network_security_group" "operators" {
  name                = "nsg-operators-${var.environment}"
  location            = azurerm_resource_group.network.location
  resource_group_name = azurerm_resource_group.network.name
  tags                = local.tags

  security_rule {
    name                       = "allow-private-service-https"
    priority                   = 100
    direction                  = "Outbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "443"
    source_address_prefix      = local.operator_cidr
    destination_address_prefix = local.private_endpoint_cidr
  }
  security_rule {
    name                       = "allow-platform-dns"
    priority                   = 110
    direction                  = "Outbound"
    access                     = "Allow"
    protocol                   = "*"
    source_port_range          = "*"
    destination_port_range     = "53"
    source_address_prefix      = local.operator_cidr
    destination_address_prefix = "AzurePlatformDNS"
  }
  security_rule {
    name                       = "deny-other-private-connectivity"
    priority                   = 200
    direction                  = "Outbound"
    access                     = "Deny"
    protocol                   = "*"
    source_port_range          = "*"
    destination_port_range     = "*"
    source_address_prefix      = "*"
    destination_address_prefix = "VirtualNetwork"
  }
}

resource "azurerm_subnet_network_security_group_association" "integration" {
  for_each                  = local.projects
  subnet_id                 = azurerm_subnet.integration[each.key].id
  network_security_group_id = azurerm_network_security_group.integration[each.key].id
}

resource "azurerm_subnet_network_security_group_association" "private_endpoints" {
  subnet_id                 = azurerm_subnet.private_endpoints.id
  network_security_group_id = azurerm_network_security_group.private_endpoints.id
}

resource "azurerm_subnet_network_security_group_association" "operators" {
  subnet_id                 = azurerm_subnet.operators.id
  network_security_group_id = azurerm_network_security_group.operators.id
}

resource "azurerm_route_table" "integration" {
  name                          = "rt-app-${var.environment}"
  location                      = azurerm_resource_group.network.location
  resource_group_name           = azurerm_resource_group.network.name
  bgp_route_propagation_enabled = false
  route                         = []
  tags                          = local.tags
}

resource "azurerm_subnet_route_table_association" "integration" {
  for_each       = local.projects
  subnet_id      = azurerm_subnet.integration[each.key].id
  route_table_id = azurerm_route_table.integration.id
}

resource "azurerm_private_dns_zone" "services" {
  for_each            = local.dns_zones
  name                = each.value
  resource_group_name = azurerm_resource_group.network.name
  tags                = local.tags
}

resource "azurerm_private_dns_zone_virtual_network_link" "services" {
  for_each              = local.dns_zones
  name                  = "link-${var.environment}-${each.key}"
  resource_group_name   = azurerm_resource_group.network.name
  private_dns_zone_name = azurerm_private_dns_zone.services[each.key].name
  virtual_network_id    = azurerm_virtual_network.shared.id
  registration_enabled  = false
  tags                  = local.tags
}
