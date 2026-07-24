from __future__ import annotations

import ast
import unittest
from pathlib import Path

from tools.validation.check_text_compatibility import check_file


ROOT = Path(__file__).resolve().parents[1]


class LoopIntegrationTests(unittest.TestCase):
    def _text(self, relative: str) -> str:
        return (ROOT / relative).read_text(encoding="utf-8")

    def test_validator_keeps_full_skill_inventory_and_loop_surfaces(self):
        path = ROOT / "tools/validation/validate_repo.py"
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        expected = None
        for node in tree.body:
            if isinstance(node, ast.Assign) and any(
                isinstance(target, ast.Name) and target.id == "EXPECTED_SKILLS" for target in node.targets
            ):
                expected = ast.literal_eval(node.value)
                break
        self.assertIsNotNone(expected)
        self.assertEqual(len(expected), 26)
        self.assertEqual(len(set(expected)), 26)
        for anchor in (
            "ds_lite_loop.py",
            "bounded-loop-protocol.md",
            "codex-autoresearch-integration-audit.zh.md",
            "email-to-codex-autoresearch-author.zh.md",
            "ds-lite.loop-contract.v1",
            "ds-lite.loop-receipt.v1",
            "no automatic retry",
            "duplicate-risk",
        ):
            self.assertIn(anchor, source)

    def test_expected_runtime_references_include_bounded_loop(self):
        source = self._text("tools/validation/validate_repo.py")
        self.assertIn('"bounded-loop-protocol.md"', source)

    def test_trusted_hook_runner_enforces_pinned_cli_identity(self):
        source = self._text("teaching/trusted_hook_run.py")
        self.assertIn('EXPECTED_CODEX_VERSION = "0.144.5"', source)
        self.assertIn("expected_cli_version=EXPECTED_CODEX_VERSION", source)
        self.assertIn("expected_cli_sha256=EXPECTED_SHA256", source)

    def test_loop_acceptance_wrappers_are_offline_ascii_and_lf(self):
        for relative in (
            "teaching/run_loop_acceptance.ps1",
            "teaching/run_loop_acceptance.sh",
        ):
            path = ROOT / relative
            self.assertTrue(path.is_file(), relative)
            result = check_file(path)
            self.assertEqual(result["status"], "passed", result["violations"])
            source = path.read_text(encoding="ascii")
            self.assertNotIn("python -c", source.lower())
            self.assertNotIn("python3 -c", source.lower())
            self.assertNotIn("@'", source)
            self.assertNotIn('@"', source)
            self.assertIn("test_loop_runner.py", source)
            self.assertIn("offline_loop_acceptance", source)
            self.assertIn("--help", source)
            self.assertIn("py_compile", source)
            self.assertNotIn("--execute", source)
            self.assertNotIn("native-codex", source)
            self.assertNotIn("codex-autoresearch", source)
            self.assertNotIn("test_count", source)

        loop_test_tree = ast.parse(self._text("tests/test_loop_runner.py"))
        discovered = [
            node
            for node in ast.walk(loop_test_tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_")
        ]
        self.assertGreaterEqual(len(discovered), 28)

    def test_powershell_run_ids_use_timestamp_and_process_id_only(self):
        for relative in (
            "teaching/run_loop_acceptance.ps1",
            "teaching/run_cross_system_validation.ps1",
            "tools/validation/run_validate.ps1",
        ):
            source = self._text(relative)
            self.assertNotIn("[Guid]::NewGuid()", source, relative)
            self.assertIn("Get-Date", source, relative)
            self.assertIn("$PID", source, relative)

    def test_validation_entries_use_clean_wrapper_and_unique_reports(self):
        for relative in (
            "tools/validation/run_validate.ps1",
            "tools/validation/run_validate.sh",
            "teaching/run_cross_system_validation.ps1",
            "teaching/run_cross_system_validation.sh",
        ):
            source = self._text(relative)
            self.assertIn("run_trusted_hook_host_clean", source, relative)
            self.assertNotIn("run_trusted_hook_host.ps1", source, relative)
            self.assertNotIn("run_trusted_hook_host.sh", source, relative)
            self.assertIn("cross-system-validation-", source, relative)
            self.assertIn("TEMP", source, relative)
            self.assertIn("TMP", source, relative)
            self.assertIn("environment-write", source, relative)

    def test_known_cross_system_files_have_consistent_line_endings(self):
        for relative in (
            "plugins/deepscientist-lite/skills/ds-lite/agents/openai.yaml",
            "plugins/deepscientist-lite/skills/ds-lite-coordinate/agents/openai.yaml",
            "teaching/cases/paradigm-comparison-case.md",
            "teaching/run_lab.ps1",
            "tools/validation/run_validate.ps1",
        ):
            result = check_file(ROOT / relative)
            self.assertNotIn("mixed-line-endings", result["violations"], relative)

    def test_unified_validation_compiles_upstream_audit_test(self):
        for relative in (
            "tools/validation/run_validate.ps1",
            "tools/validation/run_validate.sh",
        ):
            self.assertIn("tests/test_autoresearch_audit.py", self._text(relative), relative)


if __name__ == "__main__":
    unittest.main()
