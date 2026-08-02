import unittest
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch

from tools.validation.check_cross_system import _run_shell_check, run
from tools.validation.check_text_compatibility import iter_files


class CrossSystemValidationTests(unittest.TestCase):
    def test_validation_entrypoints_accept_authorized_temp_root(self) -> None:
        root = Path(__file__).resolve().parents[1]
        shell = (root / "tools" / "validation" / "run_validate.sh").read_text(encoding="utf-8")
        powershell = (root / "tools" / "validation" / "run_validate.ps1").read_text(encoding="utf-8")
        self.assertIn("TEMP_ROOT", shell)
        self.assertIn("TEMP_ROOT", powershell)

    def test_executable_shells_do_not_embed_python_source(self):
        root = Path(__file__).resolve().parents[1]
        paths = (
            root / "tools/validation/run_validate.sh",
            root / "plugins/deepscientist-lite/assets/templates/tools/ds_lite_runtime.sh",
        )
        for path in paths:
            with self.subTest(path=path.relative_to(root).as_posix()):
                text = path.read_text(encoding="ascii")
                self.assertNotIn(" -c ", text)

    def test_report_is_redacted_and_structured(self):
        root = Path(__file__).resolve().parents[1]
        report = run(root)
        self.assertEqual(report["schema_version"], "ds-lite.cross-system-validation.v1")
        self.assertFalse(report["raw_output_persisted"])
        self.assertFalse(report["absolute_root_persisted"])
        self.assertGreaterEqual(report["argv_fixtures"]["fixture_count"], 3)

    def test_blocked_findings_are_not_upgraded(self):
        root = Path(__file__).resolve().parents[1]
        report = run(root)
        if report["failure_layer"] != "none":
            self.assertEqual(report["status"], "blocked")

    def test_utf16_style_wsl_launcher_failure_is_not_shell_syntax(self):
        root = Path(__file__).resolve().parents[1]
        stderr = "B\x00a\x00s\x00h\x00/\x00S\x00e\x00r\x00v\x00i\x00c\x00e\x00/\x00C\x00r\x00e\x00a\x00t\x00e\x00I\x00n\x00s\x00t\x00a\x00n\x00c\x00e\x00/\x00E\x00_\x00A\x00C\x00C\x00E\x00S\x00S\x00_\x00D\x00E\x00N\x00I\x00E\x00D\x00"
        completed = CompletedProcess(["bash", "-n"], 1, stdout="", stderr=stderr)
        with patch("tools.validation.check_cross_system.shutil.which", return_value="bash"), patch(
            "tools.validation.check_cross_system.subprocess.run", return_value=completed
        ):
            result = _run_shell_check(root, root / "teaching/run_loop_acceptance.sh", "bash")
        self.assertEqual(result["status"], "not-observed")
        self.assertEqual(result["failure_class"], "environment")

    def test_bash_stdin_probe_failure_blocks_syntax_classification(self):
        root = Path(__file__).resolve().parents[1]
        unavailable = CompletedProcess(["bash", "-n"], 1, stdout="", stderr="launcher failed")
        with patch("tools.validation.check_cross_system.shutil.which", return_value="bash"), patch(
            "tools.validation.check_cross_system.subprocess.run", return_value=unavailable
        ) as runner:
            result = _run_shell_check(root, root / "teaching/run_loop_acceptance.sh", "bash")
        self.assertEqual(result["status"], "not-observed")
        self.assertEqual(result["failure_class"], "environment")
        self.assertEqual(runner.call_args.args[0], ["bash", "-n"])

    def test_known_good_bash_wrapper_is_passed_or_not_observed(self):
        root = Path(__file__).resolve().parents[1]
        result = _run_shell_check(root, root / "teaching/run_loop_acceptance.sh", "bash")
        self.assertIn(result["status"], {"passed", "not-observed"})

    def test_unrendered_shell_templates_are_not_syntax_checked(self):
        root = Path(__file__).resolve().parents[1]
        report = run(root)
        item = next(
            entry
            for entry in report["syntax"]
            if entry["path"] == "plugins/deepscientist-lite/assets/templates/run_analysis.sh"
        )
        self.assertEqual(item["status"], "not-observed")
        self.assertEqual(item["failure_class"], "template-source")

    def test_unrendered_powershell_templates_are_not_syntax_checked(self):
        root = Path(__file__).resolve().parents[1]
        report = run(root)
        item = next(
            entry
            for entry in report["syntax"]
            if entry["path"] == "plugins/deepscientist-lite-core/assets/templates/run_autonomy.ps1"
        )
        self.assertEqual(item["status"], "not-observed")
        self.assertEqual(item["failure_class"], "template-source")

    def test_generated_acceptance_workspaces_are_not_scanned_as_source(self) -> None:
        root = Path(__file__).resolve().parents[1]
        paths = {path.as_posix() for path in iter_files(root)}
        self.assertFalse(any("research/appserver-continuation-" in path for path in paths))
        fixture = root / "tests" / "fixtures" / "cross-system" / "handoff-20260728-continuation.json"
        self.assertTrue(fixture.is_file())
        self.assertTrue(any(path.endswith("tests/fixtures/cross-system/handoff-20260728-continuation.json") for path in paths))


if __name__ == "__main__":
    unittest.main()
