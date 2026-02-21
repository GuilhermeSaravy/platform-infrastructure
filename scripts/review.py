#!/usr/bin/env python3
"""Review tracked infrastructure drift without applying or exposing plan contents."""

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from check_config import ConfigurationError, ROOT, validate_repository
from infra import ExecutionError, discover_units, private_directory
from runtime_config import resolve_environment


def select_units(root, environment_name, selected_unit=None):
    available = discover_units(root)
    matching = {
        unit for unit in available
        if (unit.startswith("platform/") and unit.endswith("/" + environment_name))
        or (unit.startswith("projects/") and unit.split("/")[-2] == environment_name)
    }
    if selected_unit is not None:
        if selected_unit not in matching:
            raise ConfigurationError("--unit must be a discovered state directory belonging to --environment.")
        matching = {selected_unit}
    elif not {f"platform/networking/{environment_name}", f"platform/governance/{environment_name}"} <= matching:
        raise ConfigurationError("Environment review requires both its networking and governance state directories.")
    if not matching:
        raise ConfigurationError("No state directories were found for the selected environment.")

    def order(unit):
        if unit.startswith("platform/networking/"):
            return 0, unit
        if unit.endswith("/resources"):
            return 1, unit
        if unit.startswith("platform/governance/"):
            return 2, unit
        return 3, unit

    units = sorted(matching, key=order)
    if any(not (root / unit).resolve().is_relative_to(root.resolve()) for unit in units):
        raise ConfigurationError("State directories must remain inside this checkout.")
    return units


def review_environment_variables(root, units):
    environment = resolve_environment(root, require_image=any(unit.endswith("/resources") for unit in units))
    required_variables = {name: value for name, value in environment.items() if name in {
        "TF_VAR_team_group_ids", "TF_VAR_repository_root", "TF_VAR_unique_suffix", "TF_VAR_demo_image"
    }}
    for name in list(environment):
        if name.startswith(("TF_LOG", "TF_CLI_ARGS", "TF_VAR_", "TERRAGRUNT_", "TG_")) or name in {"TF_DATA_DIR", "TF_WORKSPACE"}:
            environment.pop(name)
    environment.update(required_variables)
    environment.update({"CHECKPOINT_DISABLE": "1", "TF_INPUT": "false", "TF_WORKSPACE": "default"})
    return environment


def failure_category(content):
    for marker, category in (
        ("aadsts", "authentication failed"),
        ("authorizationpermissionmismatch", "backend or data authorization failed"),
        ("authorizationfailed", "management authorization failed"),
        ("state lock", "state lock unavailable"),
        ("requestdisallowedbypolicy", "policy rejected configuration"),
        ("backend initialization required", "backend initialization required"),
    ):
        if marker in content:
            return category
    return "configuration, provider or service error"


def run_private(command, cwd, environment, runtime, allow_changes=False):
    descriptor, filename = tempfile.mkstemp(prefix="review-", suffix=".log", dir=runtime)
    try:
        with os.fdopen(descriptor, "w+b") as output:
            try:
                result = subprocess.run(command, cwd=cwd, env=environment, stdout=output,
                                        stderr=subprocess.STDOUT, check=False, timeout=900)
            except FileNotFoundError:
                return 1, "required tool unavailable; install the pinned tools"
            except subprocess.TimeoutExpired:
                return 1, "command exceeded the 15-minute review limit"
            except OSError:
                return 1, "local process or file access failed"
            if result.returncode == 0 or (allow_changes and result.returncode == 2):
                return result.returncode, ""
            output.seek(0)
            content = output.read(1048576).decode("utf-8", errors="replace").lower()
            return 1, failure_category(content)
    finally:
        Path(filename).unlink(missing_ok=True)


def review_units(root, units, environment, runtime):
    counts = {"unchanged": 0, "changes": 0, "errors": 0}
    for unit in units:
        cwd = root / unit
        status, category = run_private(["terragrunt", "init", "-input=false", "-no-color"],
                                       cwd, environment, runtime)
        if status == 0:
            status, category = run_private(
                ["terragrunt", "plan", "-detailed-exitcode", "-input=false", "-lock-timeout=5m", "-no-color"],
                cwd, environment, runtime, allow_changes=True)
        if status == 0:
            counts["unchanged"] += 1
            print(f"UNCHANGED: {unit}")
        elif status == 2:
            counts["changes"] += 1
            print(f"CHANGES: {unit}; inspect a fresh protected local plan")
        else:
            counts["errors"] += 1
            print(f"ERROR: {unit}; {category}")
    print(f"Review summary: unchanged={counts['unchanged']}, changes={counts['changes']}, errors={counts['errors']}.")
    if counts["errors"]:
        return 1
    return 2 if counts["changes"] else 0


def main(argv=None):
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--environment", choices=("dev", "prod"), required=True)
    parser.add_argument("--unit", help="Optional exact state directory within the selected environment")
    arguments = parser.parse_args(argv)
    root = ROOT.resolve()
    try:
        projects = validate_repository(root)
        units = select_units(root, arguments.environment, arguments.unit)
        environment = review_environment_variables(root, units)
        if environment.get("GITHUB_ACTIONS") == "true" and environment.get("GITHUB_REF") != "refs/heads/main":
            raise ConfigurationError("Workflow infrastructure review must run from the reviewed main branch.")
        naming = json.loads((root / "organization/naming.yaml").read_text(encoding="utf-8"))
        for project in projects.values():
            if any(capability["type"] == "object-storage" for capability in project["capabilities"]):
                if len(naming["storage"] % (project["name"], "prod", environment["PLATFORM_UNIQUE_SUFFIX"])) > 24:
                    raise ConfigurationError("Storage naming exceeds 24 characters; shorten the project name or unique suffix.")
        runtime = root / ".runtime"
        private_directory(runtime)
        return review_units(root, units, environment, runtime)
    except (ConfigurationError, ExecutionError) as error:
        print(f"Review stopped: {error}", file=sys.stderr)
    except (OSError, ValueError, KeyError, TypeError):
        print("Review stopped: local files or configuration could not be read; inspect the documented inputs.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
