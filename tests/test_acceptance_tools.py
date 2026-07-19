from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PREPARE = REPO_ROOT / "tools" / "validation" / "prepare_codex_acceptance.py"
AUDIT = REPO_ROOT / "tools" / "validation" / "audit_codex_acceptance.py"


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


class CodexAcceptanceToolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.parent = Path(tempfile.mkdtemp(prefix="ds-lite-验收 with spaces-"))

    def run_tool(self, script: Path, *args: str, expected: int = 0) -> subprocess.CompletedProcess[str]:
        completed = subprocess.run(
            [sys.executable, str(script), *args],
            cwd=REPO_ROOT,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
        )
        self.assertEqual(completed.returncode, expected, completed.stdout + completed.stderr)
        return completed

    def test_prepare_and_audit_fresh_package(self) -> None:
        output = self.parent / "acceptance package"
        record = self.parent / "audit record.json"
        self.run_tool(
            PREPARE,
            "--output",
            str(output),
            "--cachebuster",
            "test-20260705",
            "--marketplace-name",
            "ds-lite-acceptance-test",
        )

        acceptance = read_json(output / "acceptance.json")
        self.assertEqual(acceptance["schema_version"], "ds-lite.codex-acceptance.v1")
        self.assertEqual(acceptance["plugin"]["version"], "0.5.0-beta.2+codex.test-20260705")
        self.assertEqual(acceptance["plugin"]["expected_skill_count"], 7)
        self.assertEqual(len(acceptance["fixtures"]), 7)
        self.assertFalse(acceptance["safety"]["modifies_codex_configuration"])
        self.assertTrue((output / "projects" / "manual-main").is_dir())
        self.assertFalse(any(output.glob("fixtures/**/REFERENCE_ANSWER.md")))
        self.assertEqual(len(acceptance["communication_fixture"]["case_ids"]), 12)
        self.assertTrue((output / "communication" / "BLIND_AB_SCORECARD.md").is_file())
        cases = read_json(output / "communication" / "cases.json")["cases"]
        self.assertEqual(len(cases), 12)
        for case in cases:
            self.assertEqual(
                set(case),
                {"id", "task_class", "profile", "detail_mode", "language", "prompt", "expected_protected", "expected_semantic_fields"},
            )
            self.assertGreaterEqual(len(case["prompt"]), 120)
            self.assertTrue(case["expected_semantic_fields"])
            for protected in case["expected_protected"]:
                self.assertIn(protected, case["prompt"])
        copied_plugin = output / "plugins" / "deepscientist-lite"
        self.assertTrue((copied_plugin / "scripts" / "ds_lite_communication_audit.py").is_file())
        self.assertTrue((copied_plugin / "scripts" / "ds_lite_hook.py").is_file())
        self.assertTrue((copied_plugin / "hooks" / "hooks.json").is_file())
        adoption = read_json(copied_plugin / "references" / "communication" / "upstream-adoption.json")
        self.assertEqual(len(adoption["entries"]), 39)

        self.run_tool(AUDIT, "--root", str(output), "--record", str(record))
        audit = read_json(record)
        self.assertTrue(audit["package_valid"])
        self.assertFalse(audit["installation_verified"])
        self.assertFalse(audit["skill_discovery_verified"])
        self.assertIn("all seven skills are discoverable", audit["observations_required"])

        invalid_launcher = self.parent / "not-an-executable.txt"
        invalid_launcher.write_text("not executable\n", encoding="utf-8")
        probed = self.run_tool(AUDIT, "--root", str(output), "--codex-bin", str(invalid_launcher))
        probed_payload = json.loads(probed.stdout)
        self.assertTrue(probed_payload["package_valid"])
        self.assertFalse(probed_payload["host_supported"])
        self.assertEqual(probed_payload["host_probes"][0]["status"], "unavailable")

    def test_prepare_refuses_existing_output(self) -> None:
        output = self.parent / "existing"
        output.mkdir()
        self.run_tool(PREPARE, "--output", str(output), "--without-fixtures", expected=1)

    def test_audit_detects_manifest_version_mismatch(self) -> None:
        output = self.parent / "tampered package"
        self.run_tool(
            PREPARE,
            "--output",
            str(output),
            "--cachebuster",
            "test-mismatch",
            "--without-fixtures",
        )
        manifest_path = output / "plugins" / "deepscientist-lite" / ".codex-plugin" / "plugin.json"
        manifest = read_json(manifest_path)
        manifest["version"] = "0.0.0-invalid"
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

        completed = self.run_tool(AUDIT, "--root", str(output), expected=1)
        self.assertIn("plugin version differs", completed.stdout)

    def test_audit_rejects_missing_communication_attribution(self) -> None:
        output = self.parent / "communication tampered package"
        self.run_tool(
            PREPARE,
            "--output",
            str(output),
            "--cachebuster",
            "test-communication",
            "--marketplace-name",
            "ds-lite-communication-test",
        )
        notice = output / "plugins" / "deepscientist-lite" / "THIRD_PARTY_NOTICES.md"
        notice.write_text("incomplete\n", encoding="utf-8")
        completed = self.run_tool(AUDIT, "--root", str(output), expected=1)
        self.assertIn("communication runtime assets", completed.stdout)


if __name__ == "__main__":
    unittest.main()
