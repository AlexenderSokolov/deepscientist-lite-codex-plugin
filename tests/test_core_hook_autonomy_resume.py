from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "plugins" / "deepscientist-lite-core" / "scripts" / "ds_lite_hook.py"
sys.path.insert(0, str(SCRIPT.parent))
spec = importlib.util.spec_from_file_location("core_hook_autonomy_resume", SCRIPT)
assert spec and spec.loader
hook = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hook)


class CoreHookAutonomyResumeTests(unittest.TestCase):
    def test_v2_completed_summary_is_terminal_for_report_policy(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            run = root / "research" / "autonomy" / "run"
            run.mkdir(parents=True)
            (root / "research" / "autonomy" / "contract.json").write_text("{}", encoding="utf-8")
            (run / "summary.json").write_text(json.dumps({
                "schema_version": "ds-lite.autonomy-summary.v2",
                "status": "completed",
                "terminal_policy": "report",
                "release_authorized": False,
            }), encoding="utf-8")
            (run / "progress-001.json").write_text(json.dumps({"status": "completed"}), encoding="utf-8")
            self.assertEqual(hook._autonomy_stop_gaps(root), [])

    def test_v2_projection_wins_over_legacy_adapter_summary(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            run = root / "research" / "autonomy" / "run"
            run.mkdir(parents=True)
            (root / "research" / "autonomy" / "contract.json").write_text("{}", encoding="utf-8")
            (run / "summary.json").write_text(json.dumps({
                "schema_version": "ds-lite.autonomy-summary.v1",
                "status": "completed",
                "next_action": "release",
                "release_authorized": True,
            }), encoding="utf-8")
            (run / "summary-v2.json").write_text(json.dumps({
                "schema_version": "ds-lite.autonomy-summary.v2",
                "status": "completed",
                "terminal_policy": "report",
                "release_authorized": False,
                "next_action": "final-report",
            }), encoding="utf-8")
            (run / "progress-001.json").write_text(json.dumps({"status": "completed"}), encoding="utf-8")
            self.assertEqual(hook._autonomy_stop_gaps(root), [])
            self.assertIn("final-report", hook._autonomy_context(root))

    def test_stop_first_invokes_the_approved_controller_in_the_same_hook_event(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "research" / "autonomy" / "run").mkdir(parents=True)
            (root / "research" / "state").mkdir(parents=True)
            (root / "research" / "autonomy" / "contract.json").write_text("{}", encoding="utf-8")
            (root / "research" / "autonomy" / "stop-first.json").write_text(json.dumps({
                "schema_version": "ds-lite.stop-first-protocol.v1", "status": "prepared",
            }), encoding="utf-8")
            (root / "research" / "autonomy" / "run" / "summary.json").write_text(json.dumps({
                "schema_version": "ds-lite.autonomy-summary.v1", "status": "blocked",
            }), encoding="utf-8")
            (root / "research" / "autonomy" / "run" / "progress-001.json").write_text(json.dumps({
                "active_gate": "gate-a", "status": "blocked", "next_action": "resume-independent-gate",
            }), encoding="utf-8")
            with patch.object(hook, "_workspace_root", return_value=root), patch.object(hook, "_resume_autonomy_controller", return_value=(True, "autonomy/controller-completed")) as resume:
                result = hook.handle_event("stop", {"cwd": str(root)})
            resume.assert_called_once_with(root)
            self.assertTrue(result["autonomy_resume_observed"])
            self.assertEqual(result["autonomy_resume_state"], "autonomy/controller-completed")

    def test_stop_without_explicit_stop_first_only_requests_continuation(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "research" / "autonomy" / "run").mkdir(parents=True)
            (root / "research" / "state").mkdir(parents=True)
            (root / "research" / "autonomy" / "contract.json").write_text("{}", encoding="utf-8")
            (root / "research" / "autonomy" / "run" / "summary.json").write_text(json.dumps({
                "schema_version": "ds-lite.autonomy-summary.v1", "status": "blocked",
            }), encoding="utf-8")
            (root / "research" / "autonomy" / "run" / "progress-001.json").write_text(json.dumps({
                "active_gate": "gate-a", "status": "blocked", "next_action": "resume-independent-gate",
            }), encoding="utf-8")
            with patch.object(hook, "_workspace_root", return_value=root), patch.object(hook, "_resume_autonomy_controller") as resume:
                hook.handle_event("stop", {"cwd": str(root)})
            resume.assert_not_called()


if __name__ == "__main__":
    unittest.main()
