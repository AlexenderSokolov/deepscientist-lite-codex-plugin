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

import ds_lite_autonomy_v2


class CoreHookAutonomyResumeTests(unittest.TestCase):
    def _v2_contract(self, root: Path) -> dict:
        work = root / "research" / "work-unit.json"
        work.parent.mkdir(parents=True, exist_ok=True)
        work.write_text("{}", encoding="utf-8")
        approvals = root / "approvals"
        approvals.mkdir(exist_ok=True)
        (approvals / "user.md").write_text("approved\n", encoding="utf-8")
        return {
            "schema_version": "ds-lite.autonomy-contract.v2",
            "work_unit_ref": "research/work-unit.json",
            "goals": ["verify-core"],
            "gates": [{"id": "gate-a", "depends_on": [], "effect": "read"}],
            "budget": {"max_seconds": 60, "max_attempts_per_gate": 3},
            "authorization": {
                "status": "approved", "authority": "user", "ref": "approvals/user.md",
                "allowed_effects": ["read"], "release_gate": False,
            },
            "continuity": {"mode": "foreground-bounded"},
            "terminal_policy": "report",
        }

    def _write_v2_terminal(self, root: Path, run: Path) -> None:
        contract = self._v2_contract(root)
        (root / "research" / "autonomy" / "contract.json").write_text(json.dumps(contract), encoding="utf-8")
        summary = ds_lite_autonomy_v2.summarize(
            contract, status="completed", completed=["gate-a"], blocked=[], next_action="final-report"
        )
        (run / "summary-v2.json").write_text(json.dumps(summary), encoding="utf-8")

    def test_v2_completed_summary_is_terminal_for_report_policy(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            run = root / "research" / "autonomy" / "run"
            run.mkdir(parents=True)
            self._write_v2_terminal(root, run)
            (run / "progress-001.json").write_text(json.dumps({"status": "completed"}), encoding="utf-8")
            self.assertEqual(hook._autonomy_stop_gaps(root), [])

    def test_v2_projection_wins_over_legacy_adapter_summary(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            run = root / "research" / "autonomy" / "run"
            run.mkdir(parents=True)
            (run / "summary.json").write_text(json.dumps({
                "schema_version": "ds-lite.autonomy-summary.v1",
                "status": "completed",
                "next_action": "release",
                "release_authorized": True,
            }), encoding="utf-8")
            self._write_v2_terminal(root, run)
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
