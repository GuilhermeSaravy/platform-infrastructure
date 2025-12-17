locals {
  defaults = yamldecode(file("${var.repository_root}/organization/defaults.yaml"))
  naming   = yamldecode(file("${var.repository_root}/organization/naming.yaml"))
  profiles = yamldecode(file("${var.repository_root}/organization/access-profiles.yaml"))
  project  = yamldecode(file("${var.repository_root}/projects/${var.project_name}/project.yaml"))
  human_roles = {
    for item in flatten([for declaration in local.project.access : [for role in local.profiles[declaration.profile].roles : {
      team = declaration.team, profile = declaration.profile, role = role
    }] if contains(declaration.environments, var.environment)]) : "${item.team}/${item.profile}/${item.role}" => item
  }
  workload_grants = {
    for grant in local.project.workload_grants : "${grant.principal.project}/${grant.principal.environment}/${grant.principal.identity}/${grant.target.capability}/${grant.target.container}" => grant
    if grant.principal.environment == var.environment
  }
  storage_capabilities = { for capability in local.project.capabilities : capability.name => capability if capability.type == "object-storage" }
}
module "identity_mapping" {
  source         = "../../platform/identity-mapping"
  team_group_ids = var.team_group_ids
  logical_teams  = toset(keys(local.defaults.teams))
}
data "azurerm_resource_group" "project" {
  name = format(local.naming.resource_group, var.project_name, var.environment)
}
resource "azurerm_role_assignment" "team" {
  for_each             = local.human_roles
  scope                = data.azurerm_resource_group.project.id
  role_definition_name = each.value.role
  principal_id         = module.identity_mapping.groups[each.value.team]
  principal_type       = "Group"
  lifecycle {
    precondition {
      condition     = local.profiles[each.value.profile].kind == "management" && contains(local.profiles[each.value.profile].environments, var.environment)
      error_message = "Human RG access requires a management profile permitting this environment."
    }
  }
}
data "azurerm_user_assigned_identity" "source" {
  for_each            = local.workload_grants
  name                = format(local.naming.workload_identity, each.value.principal.project, each.value.principal.environment, each.value.principal.identity)
  resource_group_name = format(local.naming.resource_group, each.value.principal.project, each.value.principal.environment)
}
data "azurerm_storage_account" "destination" {
  for_each            = length(local.workload_grants) > 0 ? local.storage_capabilities : {}
  name                = format(local.naming.storage, var.project_name, var.environment, var.unique_suffix)
  resource_group_name = data.azurerm_resource_group.project.name
}
data "azurerm_storage_container" "destination" {
  for_each           = local.workload_grants
  name               = each.value.target.container
  storage_account_id = data.azurerm_storage_account.destination[each.value.target.capability].id
}
resource "azurerm_role_assignment" "workload" {
  for_each                         = local.workload_grants
  scope                            = data.azurerm_storage_container.destination[each.key].id
  role_definition_name             = one(local.profiles[each.value.profile].roles)
  principal_id                     = data.azurerm_user_assigned_identity.source[each.key].principal_id
  principal_type                   = "ServicePrincipal"
  skip_service_principal_aad_check = true
  lifecycle {
    precondition {
      condition     = each.value.profile == "object-storage-reader" && local.profiles[each.value.profile].kind == "data" && local.profiles[each.value.profile].scope == "container"
      error_message = "Workload grants support only the centrally defined object-storage-reader container profile."
    }
    precondition {
      condition     = contains(local.storage_capabilities[each.value.target.capability].azure.containers, each.value.target.container)
      error_message = "The destination must own the declared storage capability and container."
    }
    precondition {
      condition     = contains(yamldecode(file("${var.repository_root}/projects/${each.value.principal.project}/project.yaml")).environments, var.environment)
      error_message = "Workload access may not cross environments; both projects must declare the environment."
    }
  }
}
