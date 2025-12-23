#!/usr/bin/env python3
"""Resolve external environment values without writing or printing identity mappings."""
import argparse
import json
import os
import re
import sys
import uuid
from pathlib import Path

from check_config import ConfigurationError, ROOT, load_json, unique_object

GUID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\Z")
IMAGE = re.compile(r"ghcr\.io/[a-z0-9][a-z0-9-]*/[a-z0-9][a-z0-9._/-]*@sha256:[0-9a-f]{64}\Z")


def identifier(value, name):
    if not isinstance(value, str) or not GUID.fullmatch(value) or uuid.UUID(value).int == 0 or len(set(value.replace("-", "").lower())) == 1 or value.lower() == "12345678-1234-1234-1234-123456789abc":
        raise ConfigurationError(f"{name} must contain a real, nonzero UUID; replace missing or placeholder values.")
    return value


def resolve_environment(root=ROOT, source=None, workflow=None, require_image=False):
    source = dict(os.environ if source is None else source)
    workflow = source.get("GITHUB_ACTIONS") == "true" if workflow is None else workflow
    defaults = load_json(Path(root) / "organization/defaults.yaml")
    teams = defaults.get("teams") if isinstance(defaults, dict) else None
    if not isinstance(teams, dict) or not teams or not all(re.fullmatch(r"[a-z][a-z0-9-]{1,19}", team) for team in teams):
        raise ConfigurationError("Organization defaults must declare logical teams.")
    for name in ("AZURE_TENANT_ID", "AZURE_SUBSCRIPTION_ID"):
        identifier(source.get(name), name)
    client = source.get("AZURE_CLIENT_ID", "")
    if client or workflow:
        identifier(client, "AZURE_CLIENT_ID")
    try:
        mapping = json.loads(source.get("AZURE_TEAM_GROUP_IDS", ""), object_pairs_hook=unique_object)
    except (json.JSONDecodeError, TypeError):
        raise ConfigurationError("AZURE_TEAM_GROUP_IDS must be a JSON object mapping every declared team to its existing group UUID.") from None
    if not isinstance(mapping, dict) or set(mapping) != set(teams):
        raise ConfigurationError("AZURE_TEAM_GROUP_IDS must contain exactly the logical teams declared in organization/defaults.yaml.")
    for team, value in mapping.items():
        identifier(value, f"AZURE_TEAM_GROUP_IDS entry for {team}")
    if len({value.lower() for value in mapping.values()}) != len(mapping):
        raise ConfigurationError("AZURE_TEAM_GROUP_IDS must map each team to a distinct existing group.")
    suffix = source.get("PLATFORM_UNIQUE_SUFFIX", "")
    if not re.fullmatch(r"[a-z0-9]{6,10}", suffix) or suffix in {"changeme", "example", "replace", "000000", "unique"}:
        raise ConfigurationError("PLATFORM_UNIQUE_SUFFIX must be your own stable 6-10 lowercase letters/digits; check global Azure naming availability manually.")
    image = source.get("DEMO_IMAGE", "")
    if (image or require_image) and (not IMAGE.fullmatch(image) or re.search(r"(?:owner|placeholder|example|replace)", image.split("@", 1)[0]) or len(set(image.rsplit(":", 1)[-1])) == 1):
        raise ConfigurationError("DEMO_IMAGE must be a published public ghcr.io/<owner>/<image>@sha256:<64 lowercase hex> reference; replace placeholders.")
    if workflow and not (source.get("ACTIONS_ID_TOKEN_REQUEST_URL") and source.get("ACTIONS_ID_TOKEN_REQUEST_TOKEN")):
        raise ConfigurationError("GitHub OIDC variables are unavailable; grant this job id-token: write and configure the matching federated credential.")
    resolved = dict(source)
    resolved.update({
        "ARM_TENANT_ID": source["AZURE_TENANT_ID"],
        "ARM_SUBSCRIPTION_ID": source["AZURE_SUBSCRIPTION_ID"],
        "ARM_USE_AZUREAD": "true",
        "ARM_USE_OIDC": "true" if workflow else "false",
        "ARM_USE_CLI": "false" if workflow else "true",
        "TF_VAR_team_group_ids": json.dumps(mapping, separators=(",", ":")),
        "TF_VAR_repository_root": str(Path(root).resolve()),
        "TF_VAR_unique_suffix": suffix,
        "TF_IN_AUTOMATION": "true" if workflow else "false",
        "TF_INPUT": "false",
    })
    if client:
        resolved["ARM_CLIENT_ID"] = client
    elif "ARM_CLIENT_ID" in resolved:
        del resolved["ARM_CLIENT_ID"]
    if image:
        resolved["TF_VAR_demo_image"] = image
    # A stale credential must not silently override the chosen CLI/OIDC authentication path.
    for name in ("ARM_CLIENT_SECRET", "ARM_CLIENT_CERTIFICATE_PATH", "ARM_CLIENT_CERTIFICATE_PASSWORD", "ARM_ACCESS_KEY", "ARM_SAS_TOKEN", "TF_LOG", "TF_LOG_PATH", "TERRAGRUNT_DEBUG"):
        resolved.pop(name, None)
    return resolved


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--require-image", action="store_true")
    arguments = parser.parse_args()
    try:
        resolve_environment(arguments.root, require_image=arguments.require_image)
    except ConfigurationError as error:
        print(f"External configuration rejected: {error}", file=sys.stderr)
        return 1
    print("External configuration accepted; values were not displayed or written. No authentication was attempted.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
