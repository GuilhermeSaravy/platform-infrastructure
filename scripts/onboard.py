#!/usr/bin/env python3
"""Generate one reviewed project declaration from the reusable template, offline."""
import argparse
import fcntl
import json
import os
import shutil
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path

from check_config import (
    ConfigurationError, ENVIRONMENTS, NAME, PROJECT_NAME, ROOT,
    load_json, project_environments, require, validate_repository,
)


@contextmanager
def onboarding_lock(root):
    runtime = root / ".runtime"
    require(not runtime.is_symlink(), "The runtime directory must not be a symbolic link.")
    runtime.mkdir(mode=0o700, exist_ok=True)
    runtime.chmod(0o700)
    lock_path = runtime / "onboarding.lock"
    descriptor = os.open(lock_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        os.fchmod(descriptor, 0o600)
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield runtime
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def copy_contract(source, destination, environments):
    require(not source.is_symlink(), "Project/template directories must not be symbolic links.")
    destination.mkdir(parents=True)
    source_declaration = source / "project.yaml"
    require(not source_declaration.is_symlink(), "Project declarations must not be symbolic links.")
    shutil.copyfile(source_declaration, destination / "project.yaml")
    for environment in environments:
        for unit in ("resources", "access"):
            source_leaf = source / "environments" / environment / unit / "terragrunt.hcl"
            require(not any(path.is_symlink() for path in (source / "environments", source_leaf.parent.parent, source_leaf.parent, source_leaf)), "Terragrunt template paths must not be symbolic links.")
            destination_leaf = destination / "environments" / environment / unit / "terragrunt.hcl"
            destination_leaf.parent.mkdir(parents=True)
            shutil.copyfile(source_leaf, destination_leaf)


def selected_access(template, owner_team, environments, profiles):
    declarations = []
    assigned = set()
    original_owner = template["owner"]["team"]
    for declaration in template["access"]:
        team = owner_team if declaration["team"] == original_owner else declaration["team"]
        permitted = profiles[declaration["profile"]]["environments"]
        selected = [environment for environment in declaration["environments"] if environment in environments and environment in permitted and (team, environment) not in assigned]
        if selected:
            declarations.append({**declaration, "team": team, "environments": selected})
            assigned.update((team, environment) for environment in selected)
    return declarations


def create_project(root, name, owner_team="commerce-backend", environments=None, network_slot=None, cost_center=None):
    root = Path(root).resolve()
    require(isinstance(name, str) and PROJECT_NAME.fullmatch(name), "Project name must use 3-10 lowercase alphanumeric characters, starting with a letter.")
    environments = ["dev", "prod"] if environments is None else environments
    project_environments(environments, "Requested environments", ENVIRONMENTS)
    projects_directory = root / "projects"
    require(not projects_directory.is_symlink(), "The projects directory must not be a symbolic link.")
    target = projects_directory / name
    with onboarding_lock(root) as runtime:
        require(not target.exists() and not target.is_symlink(), "The project already exists; onboarding never overwrites or updates an existing directory.")
        projects = validate_repository(root)
        defaults = load_json(root / "organization/defaults.yaml")
        profiles = load_json(root / "organization/access-profiles.yaml")
        require(owner_team in defaults["teams"], "Owner must reference an existing logical team in organization/defaults.yaml.")
        selected_cost = defaults["cost_center"] if cost_center is None else cost_center
        require(isinstance(selected_cost, str) and NAME.fullmatch(selected_cost), "Cost center must follow the existing lowercase naming convention.")
        occupied = {project["azure"]["network_slot"] for project in projects.values()}
        if network_slot is None:
            network_slot = next((slot for slot in range(128) if slot not in occupied), None)
            require(network_slot is not None, "All network slots are allocated; platform engineering must review capacity before onboarding.")
        require(type(network_slot) is int and 0 <= network_slot <= 127, "Network slot must be an integer from 0 to 127.")
        require(network_slot not in occupied, "The requested network slot is already allocated; choose an unused slot or omit --network-slot.")
        template_directory = root / "templates/project"
        require(not (root / "templates").is_symlink() and not template_directory.is_symlink(), "Templates must remain inside the repository without symbolic links.")
        template = load_json(template_directory / "project.yaml")
        with tempfile.TemporaryDirectory(prefix="onboarding-", dir=runtime) as temporary:
            candidate = Path(temporary) / "candidate"
            organization = candidate / "organization"
            organization.mkdir(parents=True)
            for filename in ("defaults.yaml", "naming.yaml", "access-profiles.yaml"):
                source = root / "organization" / filename
                require(not source.is_symlink(), "Organization contract files must not be symbolic links.")
                shutil.copyfile(source, organization / filename)
            for existing_name, declaration in projects.items():
                copy_contract(projects_directory / existing_name, candidate / "projects" / existing_name, declaration["environments"])
            staged = candidate / "projects" / name
            copy_contract(template_directory, staged, environments)
            generated = {**template, "name": name, "owner": {**template["owner"], "team": owner_team}, "cost_center": selected_cost, "environments": environments, "azure": {**template["azure"], "network_slot": network_slot}}
            generated["access"] = selected_access(template, owner_team, environments, profiles)
            (staged / "project.yaml").write_text(json.dumps(generated, indent=2) + "\n", encoding="utf-8")
            validate_repository(candidate)
            # Exclusive reservation prevents replacing an existing directory, including an empty one.
            target.mkdir(mode=0o755)
            reservation = target.stat()
            try:
                require(target.stat().st_ino == reservation.st_ino, "Project destination changed during onboarding; stop concurrent edits and retry.")
                os.rename(staged, target)
            except BaseException:
                if target.is_dir() and not target.is_symlink() and target.stat().st_ino == reservation.st_ino:
                    try:
                        target.rmdir()
                    except OSError:
                        pass
                raise
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("name", help="New project name, for example inventory")
    parser.add_argument("--owner-team", default="commerce-backend")
    parser.add_argument("--environments", nargs="+", default=["dev", "prod"], choices=sorted(ENVIRONMENTS))
    parser.add_argument("--network-slot", type=int)
    parser.add_argument("--cost-center")
    arguments = parser.parse_args()
    try:
        target = create_project(ROOT, arguments.name, arguments.owner_team, arguments.environments, arguments.network_slot, arguments.cost_center)
    except ConfigurationError as error:
        print(f"Onboarding rejected: {error}", file=sys.stderr)
        return 1
    except (OSError, KeyError, TypeError):
        print("Onboarding stopped: inspect template structure, local file permissions and concurrent edits; no shared configuration was changed.", file=sys.stderr)
        return 1
    print(target.relative_to(ROOT).as_posix())
    print((target / "project.yaml").relative_to(ROOT).as_posix())
    return 0


if __name__ == "__main__":
    sys.exit(main())
