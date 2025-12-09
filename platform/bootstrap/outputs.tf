output "workflow_client_id" {
  value       = azurerm_user_assigned_identity.deployment.client_id
  sensitive   = true
  description = "Deployment UAMI client ID supplied later as AZURE_CLIENT_ID, never printed by workflows."
}

output "workflow_principal_id" {
  value       = azurerm_user_assigned_identity.deployment.principal_id
  sensitive   = true
  description = "Deployment UAMI service principal object ID; not a workload identity."
}

output "backend_storage_account_name" {
  value       = azurerm_storage_account.state.name
  sensitive   = true
  description = "State account name; normal execution derives the same name from unique_suffix."
}

output "backend_container_name" {
  value       = azurerm_storage_container.state.name
  sensitive   = true
  description = "State container name; blob leases supply Terraform state locking."
}

output "backend_resource_group_name" {
  value       = azurerm_resource_group.state.name
  sensitive   = true
  description = "Resource group retained with local bootstrap state until an explicit migration or decommission."
}
