#!/usr/bin/env python3
"""Run one allowlisted Terragrunt state with protected output and local saved plans."""
import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from check_config import ConfigurationError, ROOT, validate_repository
from runtime_config import resolve_environment


class ExecutionError(RuntimeError):
    pass


def discover_units(root):
    units = {f"platform/{component}/{environment}" for component in ("governance", "networking") for environment in ("dev", "prod")}
    for project_file in (root / "projects").glob("*/project.yaml"):
        for configuration in (project_file.parent / "environments").glob("*/*/terragrunt.hcl"):
            if configuration.parent.name in {"resources", "access"} and configuration.parent.parent.name in {"dev", "prod"}:
                units.add(configuration.parent.relative_to(root).as_posix())
    return {unit for unit in units if (root / unit / "terragrunt.hcl").is_file()}


def source_fingerprint(root):
    digest = hashlib.sha256()
    for directory in ("organization", "platform", "projects", "modules"):
        for path in sorted((root / directory).rglob("*")):
            if path.is_file() and path.suffix in {".tf", ".hcl", ".yaml", ".json"} and not any(part.startswith(".") for part in path.relative_to(root).parts):
                digest.update(path.relative_to(root).as_posix().encode())
                digest.update(path.read_bytes())
    if (root / "root.hcl").is_file():
        digest.update((root / "root.hcl").read_bytes())
    if (root / ".terraform.lock.hcl").is_file():
        digest.update((root / ".terraform.lock.hcl").read_bytes())
    return digest.hexdigest()


def private_directory(path):
    if path.is_symlink():
        raise ExecutionError("Runtime paths must not be symbolic links.")
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.chmod(0o700)


def run_protected(command, cwd, environment, runtime, retained_output=None):
    descriptor, filename = tempfile.mkstemp(prefix="command-", suffix=".log", dir=runtime)
    try:
        with os.fdopen(descriptor, "wb") as output:
            try:
                result = subprocess.run(command, cwd=cwd, env=environment, stdout=output, stderr=subprocess.STDOUT, check=False)
            except FileNotFoundError:
                raise ExecutionError("Terragrunt is unavailable; install the exact tools listed in docs/startup.md.") from None
        if result.returncode:
            content = Path(filename).read_text(encoding="utf-8", errors="replace").lower()
            hint = "Review unit configuration and permissions; run the documented manual troubleshooting steps."
            for match, message in (
                ("authorizationfailed", "Deployment identity lacks an Azure management role at the requested scope; check bootstrap roles and propagation."),
                ("authorizationpermissionmismatch", "Backend or data authorization is missing; check Blob Data Contributor and bounded propagation retries."),
                ("state lock", "State is locked; wait for the active operation and inspect the lease before considering manual force-unlock."),
                ("backend initialization required", "Initialize this exact unit first with scripts/infra.py init UNIT."),
                ("aadsts", "Authentication failed; verify tenant/subscription and the OIDC environment subject or local interactive login."),
                ("requestdisallowedbypolicy", "Azure Policy denied a resource; inspect the policy compliance record using the operator's Azure session."),
                ("already exists", "A resource name is already in use; inspect resource ownership and globally unique suffix selection."),
            ):
                if match in content:
                    hint = message
                    break
            raise ExecutionError(f"Terragrunt failed (exit {result.returncode}). {hint} Raw output was suppressed and deleted to protect identifiers and state.")
        if retained_output is not None:
            Path(filename).chmod(0o600)
            Path(filename).replace(retained_output)
    finally:
        Path(filename).unlink(missing_ok=True)


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("init", "plan", "review", "apply", "destroy"))
    parser.add_argument("unit", help="Repository-relative state directory, e.g. platform/networking/dev")
    parser.add_argument("--approve", action="store_true", help="Explicitly approve applying a reviewed saved plan or local destruction")
    arguments = parser.parse_args()
    root = ROOT.resolve()
    try:
        projects = validate_repository(root)
        if arguments.unit not in discover_units(root):
            raise ConfigurationError("UNIT must match an existing platform governance/networking or project resources/access state; bootstrap is local-only and separate.")
        unit = (root / arguments.unit).resolve()
        if not unit.is_relative_to(root):
            raise ConfigurationError("UNIT must remain inside this repository.")
        workflow = os.environ.get("GITHUB_ACTIONS") == "true"
        if workflow and os.environ.get("GITHUB_REF") != "refs/heads/main":
            raise ConfigurationError("Workflow infrastructure operations must run from the reviewed main branch.")
        if arguments.operation == "review" and workflow:
            raise ConfigurationError("Saved-plan review is local-only; plan contents must never enter GitHub Actions output or artifacts.")
        if arguments.operation == "destroy" and (workflow or not arguments.approve):
            raise ConfigurationError("Destruction is local-only and requires --approve after reviewing the scoped cleanup runbook.")
        if arguments.approve and arguments.operation in {"init", "plan", "review"}:
            raise ConfigurationError("--approve is supported only for apply or local destroy.")
        environment = resolve_environment(root, require_image="/resources" in arguments.unit)
        execution_digest = hashlib.sha256(json.dumps({key: environment.get(key, "") for key in ("ARM_TENANT_ID", "ARM_SUBSCRIPTION_ID", "ARM_CLIENT_ID", "TF_VAR_team_group_ids", "TF_VAR_unique_suffix", "TF_VAR_demo_image")}, sort_keys=True).encode()).hexdigest()
        suffix = environment["PLATFORM_UNIQUE_SUFFIX"]
        naming = json.loads((root / "organization/naming.yaml").read_text())
        for project in projects.values():
            storage = [cap for cap in project["capabilities"] if cap["type"] == "object-storage"]
            if len(storage) > 1:
                raise ConfigurationError("Each project supports one object-storage capability; split storage ownership into another project if needed.")
            if storage and len(naming["storage"] % (project["name"].replace("-", ""), "prod", suffix)) > 24:
                raise ConfigurationError("Storage account name exceeds 24 characters; shorten the project name or unique suffix using organization/naming.yaml.")
        runtime = root / ".runtime"
        plans = runtime / "plans"
        private_directory(runtime)
        private_directory(plans)
        environment.update({"CHECKPOINT_DISABLE": "1", "TF_INPUT": "false"})
        for key in list(environment):
            if key.startswith(("TF_LOG", "TF_CLI_ARGS")):
                environment.pop(key)
        plan = plans / (arguments.unit.replace("/", "--") + ".tfplan")
        metadata = plan.with_suffix(".json")
        review = plan.with_suffix(".review.txt")
        if plan.is_symlink() or metadata.is_symlink() or review.is_symlink():
            raise ExecutionError("Saved plan paths must not be symbolic links.")
        operation = arguments.operation
        if operation in {"plan", "review", "apply", "destroy"}:
            review.unlink(missing_ok=True)
        if operation == "init":
            command = ["terragrunt", "init", "-input=false"]
        elif operation == "plan":
            plan.unlink(missing_ok=True)
            metadata.unlink(missing_ok=True)
            command = ["terragrunt", "plan", "-input=false", "-lock-timeout=5m", f"-out={plan}"]
        elif operation in {"apply", "review"}:
            if not plan.is_file() or not metadata.is_file():
                raise ExecutionError("Create a saved plan first: python3 scripts/infra.py plan UNIT.")
            try:
                recorded = json.loads(metadata.read_text())
            except (OSError, json.JSONDecodeError):
                raise ExecutionError("Saved plan metadata is unreadable; create a fresh plan.") from None
            expected = {"unit": arguments.unit, "source_sha256": source_fingerprint(root), "runtime_sha256": execution_digest, "plan_sha256": hashlib.sha256(plan.read_bytes()).hexdigest()}
            if recorded != expected:
                raise ExecutionError("Saved plan/source mismatch; create a fresh plan for this unit before review or apply.")
            if operation == "review":
                command = ["terragrunt", "show", "-no-color", str(plan)]
            else:
                if not arguments.approve:
                    if workflow or not sys.stdin.isatty() or input("Apply the saved plan for this unit? Type apply: ") != "apply":
                        raise ExecutionError("Apply requires explicit approval; GitHub uses its protected environment and --approve.")
                command = ["terragrunt", "apply", "-input=false", "-lock-timeout=5m", str(plan)]
        else:
            command = ["terragrunt", "destroy", "-input=false", "-lock-timeout=5m", "-auto-approve"]
        run_protected(command, unit, environment, runtime, retained_output=review if operation == "review" else None)
        if operation == "plan":
            if not plan.is_file():
                raise ExecutionError("Terragrunt returned without the requested saved plan; inspect configuration before retrying.")
            plan.chmod(0o600)
            descriptor = os.open(metadata, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "w") as output:
                json.dump({"unit": arguments.unit, "source_sha256": source_fingerprint(root), "runtime_sha256": execution_digest, "plan_sha256": hashlib.sha256(plan.read_bytes()).hexdigest()}, output)
        elif operation in {"apply", "destroy"}:
            plan.unlink(missing_ok=True)
            metadata.unlink(missing_ok=True)
        if operation == "review":
            print(review.relative_to(root).as_posix())
            return 0
        print(f"{operation} completed for {arguments.unit}. Output was protected; saved plans stay local and are never uploaded.")
        return 0
    except (ConfigurationError, ExecutionError, OSError) as error:
        message = str(error) if isinstance(error, (ConfigurationError, ExecutionError)) else "Cannot access a required local file; inspect file permissions and installed tools."
        print(f"Operation stopped: {message}", file=sys.stderr)
        return 1
    except (KeyError, TypeError):
        print("Operation stopped: configuration has incorrect value types; compare with templates/project.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
