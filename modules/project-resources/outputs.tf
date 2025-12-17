output "contract_version" {
  value = 1
}
output "resource_group_name" {
  value = azurerm_resource_group.project.name
}
output "workload_identities" {
  sensitive = true
  value = { for name, identity in azurerm_user_assigned_identity.runtime : name => {
    resource_id  = identity.id
    principal_id = identity.principal_id
    client_id    = identity.client_id
  } }
}
output "storage_containers" {
  sensitive = true
  value = { for name, container in azurerm_storage_container.capability : name => container.resource_manager_id }
}
output "runtime_hostnames" {
  value = { for name, app in azurerm_linux_web_app.runtime : name => app.default_hostname }
}
