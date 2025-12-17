variable "team_group_ids" {
  type        = map(string)
  sensitive   = true
  description = "Existing Entra group IDs injected from AZURE_TEAM_GROUP_IDS; never manage group lifecycle."
  validation {
    condition = alltrue([for id in values(var.team_group_ids) : can(regex("^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$", id)) && id != "00000000-0000-0000-0000-000000000000"])
    error_message = "AZURE_TEAM_GROUP_IDS must map logical teams to real nonzero Entra group object IDs."
  }
}
variable "logical_teams" {
  type        = set(string)
  description = "Nonsecret logical team names declared in organization/defaults.yaml."
}
output "groups" {
  value     = var.team_group_ids
  sensitive = true
  precondition {
    condition     = toset(keys(var.team_group_ids)) == var.logical_teams
    error_message = "AZURE_TEAM_GROUP_IDS must contain exactly the declared logical teams. No group is created here."
  }
}
