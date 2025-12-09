locals {
  defaults = yamldecode(file("${var.repository_root}/organization/defaults.yaml"))
  declarations = [
    for path in fileset(var.repository_root, "projects/*/project.yaml") :
    yamldecode(file("${var.repository_root}/${path}"))
  ]
  projects = {
    for project in local.declarations : project.name => project
    if contains(project.environments, var.environment)
  }
  policy_documents = {
    for path in fileset("${var.repository_root}/organization/policies", "*.json") :
    trimsuffix(path, ".json") => jsondecode(file("${var.repository_root}/organization/policies/${path}"))
  }
  resource_groups = toset(concat(
    ["rg-platform-network-${var.environment}"],
    [for name in keys(local.projects) : "rg-${name}-${var.environment}"]
  ))
  assignments = {
    for pair in setproduct(local.resource_groups, keys(local.policy_documents)) :
    "${pair[0]}/${pair[1]}" => { resource_group = pair[0], policy = pair[1] }
  }
}

data "azurerm_resource_group" "scopes" {
  for_each = local.resource_groups
  name     = each.value
}

resource "azurerm_policy_definition" "requirements" {
  for_each     = local.policy_documents
  name         = "${local.defaults.organization_slug}-${var.environment}-${each.key}"
  policy_type  = "Custom"
  mode         = each.value.mode
  display_name = "${each.value.display_name} (${var.environment})"
  description  = each.value.description
  policy_rule  = jsonencode(each.value.policy_rule)
  parameters   = jsonencode(each.value.parameters)
  metadata = jsonencode({
    category    = "Northstar Platform"
    owner       = "platform-engineering"
    environment = var.environment
    version     = "1.0.0"
  })
}

resource "azurerm_resource_group_policy_assignment" "requirements" {
  for_each             = local.assignments
  name                 = "northstar-${each.value.policy}"
  display_name         = local.policy_documents[each.value.policy].display_name
  description          = "Platform-owned deny policy for ${each.value.resource_group}; bootstrap state is outside this scope."
  resource_group_id    = data.azurerm_resource_group.scopes[each.value.resource_group].id
  policy_definition_id = azurerm_policy_definition.requirements[each.value.policy].id
  enforce              = true
  parameters = each.value.policy == "allowed-locations" ? jsonencode({
    allowedLocations = { value = local.defaults.azure.allowed_locations }
  }) : null

  non_compliance_message {
    content = "Follow organization/policies and the project declaration: use approved regions, ownership tags, private services and Managed Identity."
  }
}
