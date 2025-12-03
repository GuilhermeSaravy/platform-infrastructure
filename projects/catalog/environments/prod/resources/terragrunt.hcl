include "root" {
  path = find_in_parent_folders("root.hcl")
}
terraform {
  source = "${get_repo_root()}//modules/project-resources"
}
inputs = {
  project_name = "catalog"
  environment  = "prod"
}
