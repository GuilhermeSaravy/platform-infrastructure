output "policy_definition_ids" {
  sensitive = true
  value       = { for name, policy in azurerm_policy_definition.requirements : name => policy.id }
  description = "Subscription-scoped custom definitions owned by this environment's governance state."
}

output "policy_assignment_ids" {
  sensitive = true
  value       = { for name, assignment in azurerm_resource_group_policy_assignment.requirements : name => assignment.id }
  description = "Deny policy assignments at owned platform and project resource groups."
}

output "governed_resource_group_ids" {
  sensitive = true
  value = { for name, group in data.azurerm_resource_group.scopes : name => group.id }
}
