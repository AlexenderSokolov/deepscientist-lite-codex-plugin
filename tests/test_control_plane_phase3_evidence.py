from __future__ import annotations

import tempfile
import unittest
import json
import platform
from unittest.mock import patch
from pathlib import Path

from teaching.control_plane_phase3_evidence import decide, file_hash, resource_probe, supervised_probe


ROOT = Path(__file__).resolve().parents[1]


class Phase3EvidenceTests(unittest.TestCase):
    def test_phase3_runners_are_write_once_and_include_all_gates(self) -> None:
        for name in ("run_control_plane_phase3.ps1", "run_control_plane_phase3.sh"):
            content = (ROOT / "tools" / "validation" / "runners" / name).read_text(encoding="utf-8")
            for required in (
                "phase3_fault_harness.py", "controller_phase3_multigate_smoke.py",
                "control_plane_phase3_evidence", "phase3-decision.json",
                "release_allowed", "git diff --check",
            ):
                self.assertIn(required, content)

    def test_phase3_runners_require_explicit_ambient_home_opt_in(self) -> None:
        powershell = (ROOT / "tools" / "validation" / "runners" / "run_control_plane_phase3.ps1").read_text(encoding="utf-8")
        bash = (ROOT / "tools" / "validation" / "runners" / "run_control_plane_phase3.sh").read_text(encoding="utf-8")
        self.assertIn("[switch]$AmbientHome", powershell)
        self.assertIn("--ambient-home", powershell)
        self.assertIn("AMBIENT_HOME", bash)
        self.assertIn("--ambient-home", bash)

    def test_phase3_runners_pin_core_validation_to_the_selected_python(self) -> None:
        powershell = (ROOT / "tools" / "validation" / "runners" / "run_control_plane_phase3.ps1").read_text(encoding="utf-8")
        bash = (ROOT / "tools" / "validation" / "runners" / "run_control_plane_phase3.sh").read_text(encoding="utf-8")
        self.assertIn("$env:PYTHON_BIN = $PythonBin", powershell)
        self.assertIn('PYTHON_BIN="$python_bin" "$repo_root/tools/validation/runners/run_validate_core.sh"', bash)

    def test_phase3_runners_preserve_worker_imports_and_capture_native_stderr(self) -> None:
        powershell = (ROOT / "tools" / "validation" / "runners" / "run_control_plane_phase3.ps1").read_text(encoding="utf-8")
        bash = (ROOT / "tools" / "validation" / "runners" / "run_control_plane_phase3.sh").read_text(encoding="utf-8")
        self.assertIn('+ ";" + $Root', powershell)
        self.assertIn('$PSNativeCommandUseErrorActionPreference = $false', powershell)
        self.assertIn('$ErrorActionPreference = "Continue"', powershell)
        self.assertIn(':$repo_root/plugins/deepscientist-lite-control-plane/controller:$repo_root', bash)

    def test_supervised_probe_recovers_same_action_and_converges(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            result = supervised_probe(
                root / "project", root / "probe-runtime", root / "probe.json",
            )
            self.assertEqual(result["status"], "passed")
            self.assertEqual(result["supervisor_generations"], 2)
            self.assertTrue(result["same_action_recovered"])
            self.assertTrue(result["all_gates_terminal"])
            self.assertTrue(result["job_terminal"])
            self.assertLessEqual(result["peak_concurrency"], 2)
            self.assertTrue(result["backup_restore_valid"])
            self.assertTrue(result["broker_journal_valid"])
            self.assertFalse(result["release_allowed"])

    def test_resource_probe_records_windows_startup_rss_cpu_and_growth(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            result = resource_probe(Path(temp) / "resource.json")
            self.assertEqual(result["status"], "passed")
            self.assertGreater(result["startup_ms"], 0)
            self.assertGreater(result["peak_rss_bytes"], 0)
            self.assertGreater(result["control_data_growth_bytes"], 0)
            self.assertEqual(result["platform"], platform.system().lower())

    def test_decision_requires_real_smoke_and_all_registered_gates(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            def emit(name: str, value: dict) -> Path:
                path = root / name
                path.write_text(json.dumps(value) + "\n", encoding="utf-8")
                return path
            fault = emit("fault.json", {"status": "passed", "seed": 20260731, "trials": 100,
                "cases": {"K10": {"all_passed": True}, "K11": {"all_passed": True}}})
            real = emit("real.json", {"status": "passed", "evidence_class": "real-app-server-external-controller-processes",
                "checks": {"exactly_two_turn_starts": True, "single_tool_side_effect": True,
                    "ttl_owner_takeover": True, "domain_terminal": True}, "controller_pids": [1, 2, 3],
                "codex_version": "0.146.0-alpha.3.1", "schema_sha256": "a" * 64,
                "model_catalog_sha256": "b" * 64})
            supervised = emit("supervised.json", {"status": "passed", "same_action_recovered": True,
                "all_gates_terminal": True, "job_terminal": True,
                "backup_restore_valid": True, "broker_journal_valid": True})
            resource = emit("resource.json", {"status": "passed", "platform": "windows"})
            # Windows PowerShell redirects native output as UTF-16LE with a BOM.
            tests = root / "tests.txt"; tests.write_text("Ran 72 tests\nOK\n", encoding="utf-16")
            support = root / "support.txt"; support.write_text("Ran 7 tests\nOK\n", encoding="utf-16")
            core = emit("core.json", {"status": "passed"})
            previous = root / "previous.json"
            previous.write_text("{\"phase3_decision\":\"no-go\"}\n", encoding="utf-8")
            with patch("teaching.control_plane_phase3_evidence.PHASE2_DECISION_SHA256", file_hash(previous)):
                result = decide(previous=previous, fault=fault, real_smoke=real,
                    supervised=supervised, resource=resource, tests=tests,
                    support_tests=support, core=core,
                    output=root / "decision.json")
            self.assertEqual(result["phase3_decision"], "go")
            self.assertTrue(result["phase4_goal_allowed"])
            self.assertFalse(result["release_allowed"])
            self.assertEqual(result["versions"]["codex_cli"], "0.146.0-alpha.3.1")
            self.assertEqual(result["digests"]["codex_schema_sha256"], "a" * 64)

            failed_real = emit("real-failed.json", {"status": "failed"})
            with patch("teaching.control_plane_phase3_evidence.PHASE2_DECISION_SHA256", file_hash(previous)):
                blocked = decide(previous=previous, fault=fault, real_smoke=failed_real,
                    supervised=supervised, resource=resource, tests=tests,
                    support_tests=support, core=core,
                    output=root / "decision-blocked.json")
            self.assertEqual(blocked["phase3_decision"], "pending-external-observation")
            self.assertFalse(blocked["phase4_goal_allowed"])


if __name__ == "__main__":
    unittest.main()
