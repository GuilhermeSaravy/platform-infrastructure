output "contract_version" {
  value = 1
}
output "assignment_ids" {
  sensitive = true
  value = {
    teams     = { for key, assignment in azurerm_role_assignment.team : key => assignment.id }
    workloads = { for key, assignment in azurerm_role_assignment.workload : key => assignment.id }
  }
}
