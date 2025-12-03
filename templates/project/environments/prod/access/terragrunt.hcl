include "root" {
  path = find_in_parent_folders("root.hcl")
}
terraform {
  source = "${get_repo_root()}//modules/project-access"
}
inputs = {
  project_name = basename(dirname(dirname(dirname(get_terragrunt_dir()))))
  environment  = "prod"
}
