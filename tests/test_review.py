"""Authored offline drift-review cases; every external command is mocked."""

import contextlib
import io
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import review
from check_config import ConfigurationError


class ReviewTests(unittest.TestCase):
    def test_environment_discovery_orders_dependencies_and_excludes_prod(self):
        units = review.select_units(ROOT, "dev")
        self.assertEqual(units[0], "platform/networking/dev")
        governance = units.index("platform/governance/dev")
        self.assertTrue(all("/prod" not in unit for unit in units))
        self.assertTrue(all(index < governance for index, unit in enumerate(units) if unit.endswith("/resources")))
        self.assertTrue(all(index > governance for index, unit in enumerate(units) if unit.endswith("/access")))
        self.assertIn("projects/catalog/environments/dev/resources", units)
        self.assertIn("projects/orders/environments/dev/access", units)

    def test_new_project_is_discovered_without_a_central_list(self):
        units = review.discover_units(ROOT) | {
            "projects/inventory/environments/dev/resources",
            "projects/inventory/environments/dev/access",
        }
        with patch.object(review, "discover_units", return_value=units):
            discovered = review.select_units(ROOT, "dev")
        self.assertIn("projects/inventory/environments/dev/resources", discovered)
        self.assertIn("projects/inventory/environments/dev/access", discovered)

    def test_selected_unit_cannot_escape_or_cross_environment(self):
        for unit in ("../outside", "platform/networking/prod", "platform/bootstrap", "unknown"):
            with self.subTest(unit=unit), self.assertRaises(ConfigurationError):
                review.select_units(ROOT, "dev", unit)
        self.assertEqual(review.select_units(ROOT, "dev", "platform/networking/dev"),
                         ["platform/networking/dev"])

    def test_missing_foundation_is_not_reported_as_clean(self):
        with patch.object(review, "discover_units", return_value={"platform/networking/dev"}):
            with self.assertRaisesRegex(ConfigurationError, "both"):
                review.select_units(ROOT, "dev")

    def test_environment_removes_debug_and_injected_cli_flags(self):
        variables = {"TF_LOG_PROVIDER": "TRACE", "TF_CLI_ARGS_plan": "-out=leak.tfplan",
                     "TERRAGRUNT_DEBUG": "true", "TG_TF_PATH": "untrusted",
                     "TERRAGRUNT_CONFIG": "untrusted.hcl", "TF_VAR_project_name": "other",
                     "TF_DATA_DIR": "/untrusted/cache", "TF_WORKSPACE": "other-state",
                     "TF_VAR_team_group_ids": "private-map", "TF_VAR_unique_suffix": "ns123456",
                     "PATH": "/trusted/tools", "PLATFORM_UNIQUE_SUFFIX": "ns123456"}
        with patch.object(review, "resolve_environment", return_value=variables):
            environment = review.review_environment_variables(ROOT, ["projects/catalog/environments/dev/resources"])
        self.assertFalse(any(name.startswith(("TF_LOG", "TF_CLI_ARGS", "TERRAGRUNT_", "TG_")) for name in environment))
        self.assertNotIn("TF_VAR_project_name", environment)
        self.assertNotIn("TF_DATA_DIR", environment)
        self.assertEqual(environment["TF_WORKSPACE"], "default")
        self.assertEqual(environment["TF_VAR_team_group_ids"], "private-map")
        self.assertEqual(environment["TF_INPUT"], "false")

    def test_plan_change_exit_is_not_a_command_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = Path(directory)
            with patch.object(review.subprocess, "run", return_value=subprocess.CompletedProcess([], 2)):
                self.assertEqual(review.run_private(["terragrunt", "plan"], ROOT, {}, runtime, allow_changes=True), (2, ""))
            self.assertEqual(list(runtime.iterdir()), [])

    def test_raw_error_and_identifiers_never_reach_output(self):
        def fail(command, **options):
            options["stdout"].write(b"AuthorizationFailed private-tenant private-group https://private.invalid")
            return subprocess.CompletedProcess(command, 1)

        with tempfile.TemporaryDirectory() as directory, patch.object(review.subprocess, "run", side_effect=fail):
            captured = io.StringIO()
            with contextlib.redirect_stdout(captured), contextlib.redirect_stderr(captured):
                result = review.review_units(ROOT, ["platform/networking/dev"], {}, Path(directory))
            self.assertEqual(result, 1)
            self.assertEqual(list(Path(directory).iterdir()), [])
        self.assertIn("management authorization failed", captured.getvalue())
        self.assertNotIn("private-tenant", captured.getvalue())
        self.assertNotIn("private-group", captured.getvalue())
        self.assertNotIn("private.invalid", captured.getvalue())

    def test_timeout_and_missing_tool_are_safe_and_cleaned_up(self):
        for exception in (FileNotFoundError("private-path"), subprocess.TimeoutExpired("private-command", 900)):
            with self.subTest(exception=type(exception).__name__), tempfile.TemporaryDirectory() as directory:
                with patch.object(review.subprocess, "run", side_effect=exception):
                    status, category = review.run_private(["terragrunt", "plan"], ROOT, {}, Path(directory))
                self.assertEqual(status, 1)
                self.assertNotIn("private", category)
                self.assertEqual(list(Path(directory).iterdir()), [])

    def test_error_precedes_changes_and_later_units_still_run(self):
        units = ["platform/networking/dev", "projects/catalog/environments/dev/resources", "platform/governance/dev"]
        results = [(0, ""), (2, ""), (1, "authentication failed"), (0, ""), (0, "")]
        with patch.object(review, "run_private", side_effect=results) as run, contextlib.redirect_stdout(io.StringIO()):
            status = review.review_units(ROOT, units, {}, ROOT / ".runtime")
        self.assertEqual(status, 1)
        self.assertEqual(run.call_count, 5)
        self.assertEqual([call.args[0][1] for call in run.call_args_list], ["init", "plan", "init", "init", "plan"])
        for call in run.call_args_list:
            command = call.args[0]
            self.assertNotIn("apply", command)
            self.assertNotIn("destroy", command)
            self.assertFalse(any(option.startswith("-out") for option in command))
            if command[1] == "plan":
                self.assertIn("-detailed-exitcode", command)
                self.assertNotIn("-refresh=false", command)

    def test_unchanged_and_change_exit_codes(self):
        for plan_status, expected in ((0, 0), (2, 2)):
            with self.subTest(plan_status=plan_status), \
                    patch.object(review, "run_private", side_effect=[(0, ""), (plan_status, "")]), \
                    contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(review.review_units(ROOT, ["platform/networking/dev"], {}, ROOT / ".runtime"), expected)

    def test_preflight_rejection_never_starts_external_tools(self):
        with patch.object(review, "validate_repository", side_effect=ConfigurationError("Invalid declaration")), \
                patch.object(review.subprocess, "run") as external, contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(review.main(["--environment", "dev"]), 1)
        external.assert_not_called()


if __name__ == "__main__":
    unittest.main()
