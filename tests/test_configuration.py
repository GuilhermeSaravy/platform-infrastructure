"""Offline rejection cases. Authored for later manual execution; no Azure calls."""
import hashlib
import json
import shutil
import sys
import tempfile
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from check_config import ConfigurationError, load_json, validate_repository
from runtime_config import resolve_environment
from infra import ExecutionError, discover_units, run_protected


class ConfigurationContractTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        shutil.copytree(ROOT / "organization", self.root / "organization")
        (self.root / "projects").mkdir()
        for name in ("catalog", "orders"):
            shutil.copytree(ROOT / "projects" / name, self.root / "projects" / name)

    def tearDown(self):
        self.temporary.cleanup()

    def edit_project(self, name, mutation):
        path = self.root / "projects" / name / "project.yaml"
        value = load_json(path)
        mutation(value)
        path.write_text(json.dumps(value))

    def test_populated_declarations_resolve_cross_project_read_contract(self):
        projects = validate_repository(self.root)
        grant = projects["orders"]["workload_grants"][0]
        self.assertEqual(grant["principal"], {"project": "catalog", "environment": "dev", "identity": "api"})
        self.assertEqual(grant["target"]["container"], "exports")
        self.assertEqual(grant["profile"], "object-storage-reader")

    def test_mistyped_team_is_rejected(self):
        self.edit_project("catalog", lambda project: project["owner"].update(team="commerce-backnd"))
        with self.assertRaisesRegex(ConfigurationError, "unknown logical team"):
            validate_repository(self.root)

    def test_contributor_profile_cannot_be_used_in_production(self):
        self.edit_project("catalog", lambda project: project["access"].append({"team": "commerce-frontend", "profile": "project-developer", "environments": ["prod"]}))
        with self.assertRaisesRegex(ConfigurationError, "not permitted"):
            validate_repository(self.root)

    def test_shared_address_slot_cannot_be_allocated_twice(self):
        self.edit_project("orders", lambda project: project["azure"].update(network_slot=0))
        with self.assertRaisesRegex(ConfigurationError, "already allocated"):
            validate_repository(self.root)

    def test_boolean_network_slot_is_rejected(self):
        self.edit_project("orders", lambda project: project["azure"].update(network_slot=True))
        with self.assertRaisesRegex(ConfigurationError, "must be an integer"):
            validate_repository(self.root)

    def test_unsupported_capability_is_rejected(self):
        self.edit_project("catalog", lambda project: project["capabilities"][0].update(type="kubernetes"))
        with self.assertRaisesRegex(ConfigurationError, "unsupported capability"):
            validate_repository(self.root)

    def test_multiple_runtime_capabilities_cannot_collide_on_app_and_plan_names(self):
        self.edit_project("catalog", lambda project: project["capabilities"].append({"name": "worker", "type": "application-runtime", "azure": {"sku": "B1", "port": 8080}}))
        with self.assertRaisesRegex(ConfigurationError, "one application-runtime"):
            validate_repository(self.root)

    def test_project_name_matches_azure_module_limits(self):
        for name in ("ab", "catalog-tool", "projecttoolong", "7catalog"):
            with self.subTest(name=name):
                path = self.root / "projects/catalog/project.yaml"
                original = path.read_text()
                self.edit_project("catalog", lambda project: project.update(name=name))
                with self.assertRaisesRegex(ConfigurationError, "3-10 lowercase alphanumeric"):
                    validate_repository(self.root)
                path.write_text(original)

    def test_reusable_onboarding_template_works_without_shared_project_list_edit(self):
        shutil.copytree(ROOT / "templates/project", self.root / "projects/inventory")
        projects = validate_repository(self.root)
        self.assertIn("inventory", projects)
        self.assertEqual(projects["inventory"]["azure"]["network_slot"], 2)

    def test_unknown_configuration_field_is_rejected(self):
        self.edit_project("catalog", lambda project: project.update(environmnts=["dev"]))
        with self.assertRaisesRegex(ConfigurationError, "unsupported fields"):
            validate_repository(self.root)

    def test_grant_rejects_unowned_container(self):
        self.edit_project("orders", lambda project: project["workload_grants"][0]["target"].update(container="not-declared"))
        with self.assertRaisesRegex(ConfigurationError, "undeclared container"):
            validate_repository(self.root)

    def test_grant_rejects_unknown_workload_identity(self):
        self.edit_project("orders", lambda project: project["workload_grants"][0]["principal"].update(identity="missing-api"))
        with self.assertRaisesRegex(ConfigurationError, "source runtime Managed Identity"):
            validate_repository(self.root)

    def test_grant_rejects_unknown_source_project(self):
        self.edit_project("orders", lambda project: project["workload_grants"][0]["principal"].update(project="missing-project"))
        with self.assertRaisesRegex(ConfigurationError, "unknown source project"):
            validate_repository(self.root)

    def test_duplicate_grant_is_rejected(self):
        self.edit_project("orders", lambda project: project["workload_grants"].append(project["workload_grants"][0].copy()))
        with self.assertRaisesRegex(ConfigurationError, "duplicate workload grants"):
            validate_repository(self.root)

    def test_storage_role_cannot_silently_expand_to_write(self):
        path = self.root / "organization/access-profiles.yaml"
        profiles = load_json(path)
        profiles["object-storage-reader"]["roles"] = ["Storage Blob Data Contributor"]
        path.write_text(json.dumps(profiles))
        with self.assertRaisesRegex(ConfigurationError, "read-only container semantics"):
            validate_repository(self.root)

    def test_malformed_json_error_does_not_echo_payload(self):
        path = self.root / "projects/catalog/project.yaml"
        path.write_text('{"sensitive-marker": INVALID}')
        with self.assertRaises(ConfigurationError) as context:
            validate_repository(self.root)
        self.assertNotIn("sensitive-marker", str(context.exception))

    def test_duplicate_json_fields_are_rejected(self):
        path = self.root / "projects/catalog/project.yaml"
        path.write_text('{"name":"catalog","name":"orders"}')
        with self.assertRaisesRegex(ConfigurationError, "duplicate keys"):
            validate_repository(self.root)

    def test_bootstrap_and_arbitrary_paths_are_not_in_normal_unit_allowlist(self):
        units = discover_units(ROOT)
        self.assertNotIn("platform/bootstrap", units)
        self.assertNotIn("../platform/bootstrap", units)
        self.assertNotIn("platform/governance", units)

    def test_failed_subprocess_output_is_deleted_and_never_in_exception(self):
        def rejected_command(*args, **kwargs):
            kwargs["stdout"].write(b"private-fixture-marker AuthorizationFailed")
            return SimpleNamespace(returncode=1)
        with patch("infra.subprocess.run", side_effect=rejected_command):
            with self.assertRaises(ExecutionError) as context:
                run_protected(["not-executed"], self.root, {}, self.root)
        self.assertNotIn("private-fixture-marker", str(context.exception))
        self.assertIn("management role", str(context.exception))
        self.assertEqual(list(self.root.glob("command-*.log")), [])

    def test_successful_review_retains_output_only_in_a_private_file(self):
        destination = self.root / "review.txt"
        def rendered_plan(*args, **kwargs):
            kwargs["stdout"].write(b"synthetic private plan contents")
            return SimpleNamespace(returncode=0)
        with patch("infra.subprocess.run", side_effect=rendered_plan):
            run_protected(["not-executed"], self.root, {}, self.root, retained_output=destination)
        self.assertEqual(destination.read_bytes(), b"synthetic private plan contents")
        self.assertEqual(destination.stat().st_mode & 0o777, 0o600)
        self.assertEqual(list(self.root.glob("command-*.log")), [])

    def test_failed_review_does_not_retain_error_output(self):
        destination = self.root / "review.txt"
        def rejected_show(*args, **kwargs):
            kwargs["stdout"].write(b"synthetic private error details")
            return SimpleNamespace(returncode=1)
        with patch("infra.subprocess.run", side_effect=rejected_show):
            with self.assertRaises(ExecutionError):
                run_protected(["not-executed"], self.root, {}, self.root, retained_output=destination)
        self.assertFalse(destination.exists())


class ExternalConfigurationTests(unittest.TestCase):
    def fixture(self):
        # Deterministic synthetic UUIDs are generated only inside the offline tests.
        teams = load_json(ROOT / "organization/defaults.yaml")["teams"]
        synthetic = lambda label: str(uuid.uuid5(uuid.NAMESPACE_DNS, "offline-test.invalid/" + label))
        return {
            "AZURE_TENANT_ID": synthetic("tenant"),
            "AZURE_SUBSCRIPTION_ID": synthetic("subscription"),
            "AZURE_CLIENT_ID": synthetic("client"),
            "AZURE_TEAM_GROUP_IDS": json.dumps({team: synthetic(team) for team in teams}),
            "PLATFORM_UNIQUE_SUFFIX": "fixture9",
            "DEMO_IMAGE": "ghcr.io/test-fixture/demo@sha256:" + hashlib.sha256(b"offline test fixture").hexdigest(),
        }

    def test_local_cli_mode_does_not_require_preexisting_deployment_identity(self):
        source = self.fixture()
        source.pop("AZURE_CLIENT_ID")
        resolved = resolve_environment(ROOT, source, workflow=False)
        self.assertNotIn("ARM_CLIENT_ID", resolved)
        self.assertEqual(resolved["ARM_USE_CLI"], "true")
        self.assertEqual(resolved["ARM_USE_OIDC"], "false")

    def test_workflow_requires_client_identity(self):
        source = self.fixture()
        source.pop("AZURE_CLIENT_ID")
        with self.assertRaisesRegex(ConfigurationError, "AZURE_CLIENT_ID"):
            resolve_environment(ROOT, source, workflow=True)

    def test_every_required_external_identity_rejects_empty_placeholder_and_zero(self):
        for name in ("AZURE_TENANT_ID", "AZURE_SUBSCRIPTION_ID", "AZURE_CLIENT_ID"):
            for value in ("", "<replace-me>", "00000000-0000-0000-0000-000000000000", "11111111-1111-1111-1111-111111111111"):
                with self.subTest(name=name, value=value):
                    source = self.fixture()
                    source[name] = value
                    with self.assertRaisesRegex(ConfigurationError, name):
                        resolve_environment(ROOT, source, workflow=True)

    def test_mapping_requires_exact_team_keys(self):
        source = self.fixture()
        source["AZURE_TEAM_GROUP_IDS"] = "{}"
        with self.assertRaisesRegex(ConfigurationError, "exactly the logical teams"):
            resolve_environment(ROOT, source, workflow=False)

    def test_malformed_mapping_does_not_echo_input(self):
        source = self.fixture()
        source["AZURE_TEAM_GROUP_IDS"] = "private-value-this-is-not-json"
        with self.assertRaises(ConfigurationError) as context:
            resolve_environment(ROOT, source, workflow=False)
        self.assertNotIn("private-value", str(context.exception))

    def test_mapping_rejects_placeholder_group_value(self):
        source = self.fixture()
        mapping = json.loads(source["AZURE_TEAM_GROUP_IDS"])
        mapping["commerce-backend"] = "<backend-group-object-id>"
        source["AZURE_TEAM_GROUP_IDS"] = json.dumps(mapping)
        with self.assertRaisesRegex(ConfigurationError, "commerce-backend"):
            resolve_environment(ROOT, source, workflow=False)

    def test_workflow_requires_oidc_job_permission(self):
        with self.assertRaisesRegex(ConfigurationError, "id-token: write"):
            resolve_environment(ROOT, self.fixture(), workflow=True)

    def test_workflow_uses_native_oidc_and_never_a_client_secret(self):
        source = self.fixture()
        source.update(ACTIONS_ID_TOKEN_REQUEST_URL="https://oidc.invalid", ACTIONS_ID_TOKEN_REQUEST_TOKEN="synthetic-test-only", ARM_CLIENT_SECRET="must-be-removed")
        resolved = resolve_environment(ROOT, source, workflow=True)
        self.assertEqual(resolved["ARM_USE_OIDC"], "true")
        self.assertEqual(resolved["ARM_USE_CLI"], "false")
        self.assertNotIn("ARM_CLIENT_SECRET", resolved)

    def test_stale_runtime_overrides_cannot_change_leaf_intent_or_state_workspace(self):
        source = self.fixture()
        stale = {
            "TF_VAR_environment": "prod",
            "TF_VAR_project_name": "differentproject",
            "TF_VAR_team_group_ids": "stale mapping",
            "TF_VAR_repository_root": "/different/checkout",
            "TF_VAR_unique_suffix": "stalesuffix",
            "TF_VAR_demo_image": "stale image",
            "TG_TF_PATH": "/different/terraform",
            "TERRAGRUNT_TFPATH": "/different/terraform",
            "TERRAGRUNT_DEBUG": "true",
            "TF_CLI_ARGS": "-unsafe",
            "TF_CLI_ARGS_plan": "-target=other",
            "TF_LOG": "TRACE",
            "TF_LOG_PATH": "/unprotected/log",
            "TF_DATA_DIR": "/different/state",
            "TF_WORKSPACE": "prod",
            "ARM_USE_MSI": "true",
            "ARM_USE_AKS_WORKLOAD_IDENTITY": "true",
            "ARM_OIDC_TOKEN": "stale token",
            "ARM_OIDC_TOKEN_FILE_PATH": "/different/token",
            "ARM_OIDC_REQUEST_URL": "https://different.invalid",
            "ARM_OIDC_REQUEST_TOKEN": "stale request token",
            "AZURE_CONFIG_DIR": "/private/interactive-cli-session",
        }
        source.update(stale)
        resolved = resolve_environment(ROOT, source, workflow=False)
        for name in stale:
            if name not in {"TF_VAR_team_group_ids", "TF_VAR_repository_root", "TF_VAR_unique_suffix", "TF_VAR_demo_image", "TF_WORKSPACE", "ARM_USE_MSI", "ARM_USE_AKS_WORKLOAD_IDENTITY", "AZURE_CONFIG_DIR"}:
                self.assertNotIn(name, resolved)
        self.assertEqual({name for name in resolved if name.startswith("TF_VAR_")}, {"TF_VAR_team_group_ids", "TF_VAR_repository_root", "TF_VAR_unique_suffix", "TF_VAR_demo_image"})
        self.assertEqual(json.loads(resolved["TF_VAR_team_group_ids"]), json.loads(source["AZURE_TEAM_GROUP_IDS"]))
        self.assertEqual(resolved["TF_VAR_unique_suffix"], source["PLATFORM_UNIQUE_SUFFIX"])
        self.assertEqual(resolved["TF_VAR_demo_image"], source["DEMO_IMAGE"])
        self.assertEqual(resolved["TF_WORKSPACE"], "default")
        self.assertEqual(resolved["ARM_USE_MSI"], "false")
        self.assertEqual(resolved["ARM_USE_AKS_WORKLOAD_IDENTITY"], "false")
        self.assertEqual(resolved["AZURE_CONFIG_DIR"], source["AZURE_CONFIG_DIR"])

    def test_mutable_or_placeholder_image_is_rejected(self):
        for image in ("ghcr.io/test-fixture/demo:latest", "ghcr.io/owner/image@sha256:" + "0" * 64):
            source = self.fixture()
            source["DEMO_IMAGE"] = image
            with self.assertRaisesRegex(ConfigurationError, "DEMO_IMAGE"):
                resolve_environment(ROOT, source, workflow=False, require_image=True)


if __name__ == "__main__":
    unittest.main()
