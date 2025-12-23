#!/usr/bin/env python3
"""Check committed logical declarations without Azure access or third-party packages."""
import argparse
import ipaddress
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NAME = re.compile(r"[a-z][a-z0-9-]{1,19}\Z")
PROJECT_NAME = re.compile(r"[a-z][a-z0-9]{2,9}\Z")
ENVIRONMENTS = {"dev", "prod"}


class ConfigurationError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise ConfigurationError(message)


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "JSON objects must not contain duplicate keys.")
        result[key] = value
    return result


def load_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique_object)
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise ConfigurationError(f"Cannot read {path.name}: supply valid JSON (a YAML subset).") from None


def fields(value, allowed, required, context):
    require(isinstance(value, dict), f"{context} must be an object.")
    require(not (set(value) - set(allowed)), f"{context} contains unsupported fields.")
    require(set(required) <= set(value), f"{context} is missing required fields.")


def unique_list(value, context, nonempty=True):
    require(isinstance(value, list), f"{context} must be a list.")
    require(not nonempty or bool(value), f"{context} must not be empty.")
    require(all(isinstance(item, str) for item in value), f"{context} entries must be strings.")
    require(len(set(value)) == len(value), f"{context} contains duplicate entries.")
    return value


def project_environments(value, context, supported):
    values = unique_list(value, context)
    require(set(values) <= set(supported), f"{context} references an undeclared environment.")
    return values


def _validate_repository(root):
    root = Path(root)
    defaults = load_json(root / "organization/defaults.yaml")
    profiles_document = load_json(root / "organization/access-profiles.yaml")
    fields(defaults, {"organization", "organization_slug", "cost_center", "environments", "teams", "azure", "tags"}, {"organization", "organization_slug", "cost_center", "environments", "teams", "azure", "tags"}, "Organization defaults")
    require(isinstance(defaults["organization"], str) and bool(defaults["organization"]), "Organization display name is required.")
    require(isinstance(defaults["organization_slug"], str) and NAME.fullmatch(defaults["organization_slug"]), "Organization slug must follow lowercase naming conventions.")
    teams = defaults.get("teams")
    require(isinstance(teams, dict) and teams, "Organization teams must be a nonempty map.")
    require(all(isinstance(team, str) and NAME.fullmatch(team) for team in teams), "Team names must use lowercase naming conventions.")
    for team, options in teams.items():
        fields(options, {"group_name"}, {"group_name"}, "Organization logical team")
        require(options["group_name"] == "grp-" + team, "Prerequisite group names must follow grp-<logical-team>.")
    environments = unique_list(defaults.get("environments"), "Organization environments")
    require(set(environments) == ENVIRONMENTS, "Organization environments must declare dev and prod.")
    profiles = profiles_document
    require(isinstance(profiles, dict) and profiles, "Access profiles must be a nonempty map.")
    for profile in profiles.values():
        fields(profile, {"kind", "roles", "scope", "description", "environments"}, {"kind", "roles", "scope", "environments"}, "Access profile")
        unique_list(profile["roles"], "Access profile roles")
        project_environments(profile["environments"], "Access profile environments", ENVIRONMENTS)
        require((profile["kind"], profile["scope"]) in {("management", "project-resource-group"), ("data", "container")}, "Access profile kind/scope is unsupported.")
    azure = defaults["azure"]
    fields(azure, {"location", "allowed_locations", "network_cidrs"}, {"location", "allowed_locations", "network_cidrs"}, "Organization Azure options")
    locations = unique_list(azure["allowed_locations"], "Allowed Azure locations")
    require(azure["location"] in locations, "Default Azure region must be allowed by policy.")
    require(set(azure["network_cidrs"]) == ENVIRONMENTS, "Each environment needs its own shared network CIDR.")
    try:
        networks = [ipaddress.ip_network(azure["network_cidrs"][environment]) for environment in sorted(ENVIRONMENTS)]
    except ValueError:
        raise ConfigurationError("Environment network CIDRs must be valid, aligned IP networks.") from None
    require(all(network.version == 4 and network.prefixlen == 16 for network in networks), "Shared networks require IPv4 /16 CIDRs for the audited subnet allocation.")
    require(not networks[0].overlaps(networks[1]), "Dev and prod shared network CIDRs must not overlap.")
    require(isinstance(defaults["tags"], dict) and all(isinstance(key, str) and isinstance(value, str) for key, value in defaults["tags"].items()), "Organization tags must map strings to strings.")
    naming = load_json(root / "organization/naming.yaml")
    require(isinstance(naming, dict) and "storage" in naming, "Organization naming must define storage.")
    naming_slots = {"resource_group": 2, "network_resource_group": 1, "virtual_network": 1, "runtime": 3, "service_plan": 2, "workload_identity": 3, "storage": 3, "integration_subnet": 1, "private_endpoint_subnet": 0, "operator_subnet": 0}
    fields(naming, naming_slots, naming_slots, "Organization naming")
    require(all(isinstance(value, str) and value.count("%s") == naming_slots[key] and "%" not in value.replace("%s", "") for key, value in naming.items()), "Naming templates must use the documented number of %s substitutions.")
    project_files = sorted((root / "projects").glob("*/project.yaml"))
    require(bool(project_files), "At least one projects/<name>/project.yaml is required.")
    projects = {}
    slots = set()
    for path in project_files:
        project = load_json(path)
        context = f"Project {path.parent.name}"
        fields(project, {"name", "owner", "cost_center", "environments", "capabilities", "access", "workload_grants", "azure"}, {"name", "owner", "cost_center", "environments", "capabilities", "access", "azure"}, context)
        name = project["name"]
        require(isinstance(name, str) and PROJECT_NAME.fullmatch(name), f"{context} name must use 3-10 lowercase alphanumeric characters, starting with a letter.")
        require(name == path.parent.name and name not in projects, f"{context} name must match its unique directory.")
        fields(project["owner"], {"team"}, {"team"}, f"{context} owner")
        require(project["owner"]["team"] in teams, f"{context} owner references an unknown logical team.")
        require(isinstance(project["cost_center"], str) and bool(NAME.fullmatch(project["cost_center"])), f"{context} requires a lowercase cost_center.")
        envs = project_environments(project["environments"], f"{context} environments", ENVIRONMENTS)
        fields(project["azure"], {"network_slot"}, {"network_slot"}, f"{context} Azure options")
        slot = project["azure"]["network_slot"]
        require(type(slot) is int and 0 <= slot <= 127, f"{context} network_slot must be an integer from 0 to 127.")
        require(slot not in slots, f"{context} network_slot is already allocated.")
        slots.add(slot)
        require(isinstance(project["capabilities"], list) and project["capabilities"], f"{context} needs capabilities.")
        capabilities = {}
        storage_count = 0
        runtime_count = 0
        for capability in project["capabilities"]:
            fields(capability, {"name", "type", "azure"}, {"name", "type", "azure"}, f"{context} capability")
            cap_name = capability["name"]
            require(isinstance(cap_name, str) and NAME.fullmatch(cap_name) and cap_name not in capabilities, f"{context} capability names must be valid and unique.")
            if capability["type"] == "application-runtime":
                runtime_count += 1
                require(runtime_count <= 1, f"{context} supports one application-runtime capability.")
                fields(capability["azure"], {"sku", "port"}, {"sku", "port"}, f"{context} runtime Azure options")
                require(capability["azure"]["sku"] == "B1", f"{context} runtime sku must be audited B1.")
                require(type(capability["azure"]["port"]) is int and capability["azure"]["port"] == 8080, f"{context} runtime port must match demo port 8080.")
            elif capability["type"] == "object-storage":
                storage_count += 1
                require(storage_count <= 1, f"{context} supports one object-storage capability.")
                fields(capability["azure"], {"account_tier", "replication_type", "containers"}, {"account_tier", "replication_type", "containers"}, f"{context} storage Azure options")
                require(capability["azure"]["account_tier"] == "Standard" and capability["azure"]["replication_type"] == "LRS", f"{context} storage must use audited Standard/LRS.")
                containers = unique_list(capability["azure"]["containers"], f"{context} containers")
                require(all(re.fullmatch(r"[a-z0-9](?:[a-z0-9]|-(?!-)){1,61}[a-z0-9]", item) for item in containers), f"{context} containers require valid Azure names of 3-63 characters.")
            else:
                raise ConfigurationError(f"{context} contains an unsupported capability type.")
            capabilities[cap_name] = capability
        require(isinstance(project["access"], list), f"{context} access must be a list.")
        access_keys = set()
        for access in project["access"]:
            fields(access, {"team", "profile", "environments"}, {"team", "profile", "environments"}, f"{context} access")
            require(access["team"] in teams, f"{context} access references an unknown team.")
            require(access["profile"] in profiles and access["profile"] != "object-storage-reader", f"{context} team access requires a supported project management profile.")
            selected = project_environments(access["environments"], f"{context} access environments", envs)
            profile = profiles[access["profile"]]
            require(profile.get("kind") == "management" and profile.get("scope") == "project-resource-group", f"{context} team access requires a management profile at project resource group scope.")
            require(set(selected) <= set(profile.get("environments", [])), f"{context} profile is not permitted in the selected environment.")
            for environment in selected:
                key = (access["team"], environment)
                require(key not in access_keys, f"{context} contains duplicate team access declarations.")
                access_keys.add(key)
        for environment in envs:
            for unit in ("resources", "access"):
                require((path.parent / "environments" / environment / unit / "terragrunt.hcl").is_file(), f"{context} needs environments/{environment}/{unit}/terragrunt.hcl.")
        project["_capabilities"] = capabilities
        projects[name] = project
    grants_seen = set()
    for name, destination in projects.items():
        grants = destination.get("workload_grants", [])
        require(isinstance(grants, list), f"Project {name} workload_grants must be a list.")
        for grant in grants:
            fields(grant, {"principal", "target", "profile"}, {"principal", "target", "profile"}, f"Project {name} workload grant")
            fields(grant["principal"], {"project", "environment", "identity"}, {"project", "environment", "identity"}, f"Project {name} grant principal")
            fields(grant["target"], {"capability", "container"}, {"capability", "container"}, f"Project {name} grant target")
            principal = grant["principal"]
            source = projects.get(principal["project"])
            require(source is not None, f"Project {name} grant references an unknown source project.")
            environment = principal["environment"]
            require(environment in source["environments"] and environment in destination["environments"], f"Project {name} grant requires the same declared source/destination environment.")
            identity = source["_capabilities"].get(principal["identity"])
            require(identity is not None and identity["type"] == "application-runtime", f"Project {name} grant requires a source runtime Managed Identity.")
            target = destination["_capabilities"].get(grant["target"]["capability"])
            require(target is not None and target["type"] == "object-storage", f"Project {name} grant requires a destination storage capability.")
            require(grant["target"]["container"] in target["azure"]["containers"], f"Project {name} grant targets an undeclared container.")
            require(grant["profile"] == "object-storage-reader" and grant["profile"] in profiles, f"Project {name} workload grant must use object-storage-reader.")
            profile = profiles[grant["profile"]]
            require(profile["kind"] == "data" and profile["scope"] == "container" and profile["roles"] == ["Storage Blob Data Reader"] and environment in profile["environments"], f"Project {name} storage-reader profile must preserve read-only container semantics in this environment.")
            key = (name, principal["project"], environment, principal["identity"], grant["target"]["capability"], grant["target"]["container"], grant["profile"])
            require(key not in grants_seen, f"Project {name} contains duplicate workload grants.")
            grants_seen.add(key)
    return projects


def validate_repository(root=ROOT):
    try:
        return _validate_repository(root)
    except (TypeError, KeyError, AttributeError):
        raise ConfigurationError("Declaration values have incorrect types; compare with templates/project.") from None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    arguments = parser.parse_args()
    try:
        projects = validate_repository(arguments.root)
    except (ConfigurationError, TypeError, KeyError) as error:
        message = str(error) if isinstance(error, ConfigurationError) else "Declaration values have incorrect types; compare with templates/project."
        print(f"Configuration rejected: {message}", file=sys.stderr)
        return 1
    print(f"Logical configuration accepted for {len(projects)} projects. Azure behavior remains unverified.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
