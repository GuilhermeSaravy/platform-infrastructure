"""Offline onboarding acceptance cases authored for later manual execution."""
import json
import os
import shutil
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from check_config import ConfigurationError, load_json, validate_repository
from onboard import create_project


class OnboardingTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        for directory in ("organization", "templates"):
            shutil.copytree(ROOT / directory, self.root / directory)
        (self.root / "projects").mkdir()
        for name in ("catalog", "orders"):
            shutil.copytree(ROOT / "projects" / name, self.root / "projects" / name)

    def tearDown(self):
        self.temporary.cleanup()

    def existing_contracts(self):
        return {path.relative_to(self.root).as_posix(): path.read_bytes() for directory in ("organization", "projects", "templates") for path in (self.root / directory).rglob("*") if path.is_file()}

    def test_populated_onboarding_needs_no_external_accounts_and_changes_only_new_project(self):
        before = self.existing_contracts()
        with patch.dict(os.environ, {}, clear=True):
            destination = create_project(self.root, "inventory")
        projects = validate_repository(self.root)
        project = projects["inventory"]
        self.assertEqual(project["owner"]["team"], "commerce-backend")
        self.assertEqual(project["cost_center"], "commerce-platform")
        self.assertEqual(project["environments"], ["dev", "prod"])
        self.assertEqual(project["azure"]["network_slot"], 2)
        self.assertEqual(project["workload_grants"], [])
        self.assertEqual(before, {name: (self.root / name).read_bytes() for name in before})
        self.assertEqual(destination, self.root / "projects/inventory")
        for environment in ("dev", "prod"):
            for unit in ("resources", "access"):
                leaf = destination / "environments" / environment / unit / "terragrunt.hcl"
                self.assertIn("basename(dirname(dirname(dirname(get_terragrunt_dir()))))", leaf.read_text())

    def test_selected_environment_leaves_and_access_are_complete(self):
        destination = create_project(self.root, "inventory", environments=["prod"], network_slot=9)
        project = load_json(destination / "project.yaml")
        self.assertEqual(project["azure"]["network_slot"], 9)
        self.assertEqual(project["environments"], ["prod"])
        self.assertFalse((destination / "environments/dev").exists())
        self.assertTrue((destination / "environments/prod/access/terragrunt.hcl").is_file())
        self.assertTrue(all(access["environments"] == ["prod"] and access["profile"] != "project-developer" for access in project["access"]))
        validate_repository(self.root)

    def test_owner_override_reuses_existing_team_without_duplicate_roles(self):
        destination = create_project(self.root, "inventory", owner_team="commerce-frontend")
        project = load_json(destination / "project.yaml")
        self.assertEqual(project["owner"]["team"], "commerce-frontend")
        owner_access = [access for access in project["access"] if access["team"] == "commerce-frontend"]
        self.assertIn({"team": "commerce-frontend", "profile": "project-developer", "environments": ["dev"]}, owner_access)
        self.assertIn({"team": "commerce-frontend", "profile": "project-reader", "environments": ["prod"]}, owner_access)
        validate_repository(self.root)

    def test_existing_project_is_never_overwritten(self):
        before = self.existing_contracts()
        with self.assertRaisesRegex(ConfigurationError, "never overwrites"):
            create_project(self.root, "catalog")
        self.assertEqual(before, self.existing_contracts())

    def test_existing_empty_directory_is_never_replaced(self):
        destination = self.root / "projects/inventory"
        destination.mkdir()
        inode = destination.stat().st_ino
        with self.assertRaisesRegex(ConfigurationError, "never overwrites"):
            create_project(self.root, "inventory")
        self.assertEqual(destination.stat().st_ino, inode)
        self.assertEqual(list(destination.iterdir()), [])

    def test_existing_slot_is_never_reused(self):
        before = self.existing_contracts()
        with self.assertRaisesRegex(ConfigurationError, "already allocated"):
            create_project(self.root, "inventory", network_slot=1)
        self.assertEqual(before, self.existing_contracts())

    def test_invalid_owner_is_rejected_before_project_creation(self):
        with self.assertRaisesRegex(ConfigurationError, "existing logical team"):
            create_project(self.root, "inventory", owner_team="unknown-team")
        self.assertFalse((self.root / "projects/inventory").exists())

    def test_invalid_name_and_slot_are_rejected(self):
        for name in ("../inventory", "new-project", "ab", "toolongproject"):
            with self.subTest(name=name), self.assertRaises(ConfigurationError):
                create_project(self.root, name)
        for slot in (-1, 128, True):
            with self.subTest(slot=slot), self.assertRaises(ConfigurationError):
                create_project(self.root, "inventory", network_slot=slot)

    def test_invalid_template_is_not_silently_discarded_or_installed(self):
        template = self.root / "templates/project/project.yaml"
        value = load_json(template)
        value["unsupported_option"] = "must-be-reviewed"
        template.write_text(json.dumps(value))
        before = self.existing_contracts()
        with self.assertRaisesRegex(ConfigurationError, "unsupported fields"):
            create_project(self.root, "inventory")
        self.assertFalse((self.root / "projects/inventory").exists())
        self.assertEqual(before, self.existing_contracts())

    def test_parallel_generators_allocate_distinct_slots(self):
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda name: create_project(self.root, name), ("inventory", "payments")))
        self.assertEqual({path.name for path in results}, {"inventory", "payments"})
        projects = validate_repository(self.root)
        self.assertEqual({projects[name]["azure"]["network_slot"] for name in ("inventory", "payments")}, {2, 3})


if __name__ == "__main__":
    unittest.main()
