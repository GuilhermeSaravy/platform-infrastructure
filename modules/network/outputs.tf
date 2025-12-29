output "contract_version" {
  value       = 1
  description = "Version of the narrow shared-network output contract."
}

output "resource_group_name" {
  value = azurerm_resource_group.network.name
}

output "resource_group_id" {
  sensitive = true
  value = azurerm_resource_group.network.id
}

output "virtual_network_id" {
  sensitive = true
  value = azurerm_virtual_network.shared.id
}

output "virtual_network_name" {
  value = azurerm_virtual_network.shared.name
}

output "address_space" {
  value = [local.network_cidr]
}

output "integration_subnet_ids" {
  sensitive = true
  value = { for name, subnet in azurerm_subnet.integration : name => subnet.id }
  depends_on = [
    azurerm_subnet_network_security_group_association.integration,
    azurerm_subnet_route_table_association.integration
  ]
}

output "integration_subnet_cidrs" {
  value = local.integration_cidrs
}

output "private_endpoint_subnet_id" {
  sensitive = true
  value      = azurerm_subnet.private_endpoints.id
  depends_on = [azurerm_subnet_network_security_group_association.private_endpoints]
}

output "private_endpoint_subnet_cidr" {
  value = local.private_endpoint_cidr
}

output "operator_subnet_id" {
  sensitive = true
  value      = azurerm_subnet.operators.id
  depends_on = [azurerm_subnet_network_security_group_association.operators]
}

output "operator_subnet_cidr" {
  value = local.operator_cidr
}

output "private_dns_zone_ids" {
  sensitive = true
  value      = { for name, zone in azurerm_private_dns_zone.services : name => zone.id }
  depends_on = [azurerm_private_dns_zone_virtual_network_link.services]
}

output "route_table_id" {
  sensitive = true
  value = azurerm_route_table.integration.id
}
