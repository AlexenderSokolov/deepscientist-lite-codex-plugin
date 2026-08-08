import tempfile
import unittest
import sys
import json
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "plugins" / "deepscientist-lite-core" / "scripts"))
import ds_lite_autonomy_v2

HOOK_PATH = ROOT / "plugins" / "deepscientist-lite-core" / "scripts" / "ds_lite_hook.py"
HOOK_SPEC = importlib.util.spec_from_file_location("autonomy_v2_hook", HOOK_PATH)
assert HOOK_SPEC and HOOK_SPEC.loader
ds_lite_hook = importlib.util.module_from_spec(HOOK_SPEC)
HOOK_SPEC.loader.exec_module(ds_lite_hook)


class AutonomyContractV2Tests(unittest.TestCase):
    def contract(self, root: Path, **overrides):
        work = root / "research" / "work-unit.json"
        work.parent.mkdir(parents=True, exist_ok=True)
        work.write_text("{}", encoding="utf-8")
        value = {
            "schema_version": "ds-lite.autonomy-contract.v2",
            "work_unit_ref": "research/work-unit.json",
            "goals": ["verify-core"],
            "gates": [{"id": "gate-a", "depends_on": [], "effect": "read"}],
            "budget": {"max_seconds": 60, "max_attempts_per_gate": 3},
            "authorization": {
                "status": "approved",
                "authority": "user",
                "ref": "approvals/user.md",
                "allowed_effects": ["read"],
                "release_gate": False,
            },
            "continuity": {"mode": "foreground-bounded"},
            "terminal_policy": "report",
        }
        value.update(overrides)
        return value

    def test_report_contract_does_not_grant_release(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            value = ds_lite_autonomy_v2.validate_contract(self.contract(root), project_root=root)
            summary = ds_lite_autonomy_v2.summarize(value, status="completed", completed=["gate-a"], blocked=[], next_action="handoff")
            self.assertFalse(summary["release_authorized"])
            self.assertEqual(summary["next_action"], "handoff")

    def test_release_requires_formal_gate(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            value = self.contract(root, terminal_policy="release")
            with self.assertRaises(ds_lite_autonomy_v2.AutonomyV2Error):
                ds_lite_autonomy_v2.validate_contract(value, project_root=root)

    def test_release_effect_cannot_bypass_authorization(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            value = self.contract(
                root,
                gates=[{"id": "gate-a", "depends_on": [], "effect": "release"}],
                terminal_policy="report",
            )
            with self.assertRaisesRegex(ds_lite_autonomy_v2.AutonomyV2Error, "effect"):
                ds_lite_autonomy_v2.validate_contract(value, project_root=root)

    def test_foreground_runner_fails_closed_without_execution_projection(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            contract_path = root / "contract.json"
            output = root / "run"
            contract_path.write_text(json.dumps(self.contract(root)), encoding="utf-8")
            result = ds_lite_autonomy_v2.run_foreground(root, contract_path, output)
            self.assertEqual(result["status"], "blocked")
            self.assertEqual(result["next_action"], "awaiting-user-action")
            self.assertFalse(result["release_authorized"])

    def test_foreground_runner_projects_success_to_v2_summary(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "approvals").mkdir(parents=True)
            (root / "approvals" / "user.md").write_text("approved\n", encoding="utf-8")
            (root / "runner.py").write_text(
                "import json, pathlib, sys\n"
                "path = pathlib.Path(sys.argv[1])\n"
                "path.parent.mkdir(parents=True, exist_ok=True)\n"
                "path.write_text(json.dumps({'status': 'passed'}), encoding='utf-8')\n",
                encoding="utf-8",
            )
            execution = {
                "schema_version": "ds-lite.autonomy-execution.v1",
                "gates": {
                    "gate-a": {
                        "command": [sys.executable, "runner.py", "receipts/gate-a-{attempt}.json"],
                        "receipt_ref": "receipts/gate-a-{attempt}.json",
                        "retry_class": "none",
                    }
                },
            }
            value = self.contract(root, execution=execution)
            contract_path = root / "research" / "autonomy" / "contract.json"
            output = root / "research" / "autonomy" / "run"
            contract_path.parent.mkdir(parents=True, exist_ok=True)
            contract_path.write_text(json.dumps(value), encoding="utf-8")
            result = ds_lite_autonomy_v2.run_foreground(root, contract_path, output)
            self.assertEqual(result["status"], "completed")
            self.assertEqual(result["schema_version"], "ds-lite.autonomy-summary.v2")
            self.assertEqual(result["terminal_policy"], "report")
            self.assertFalse(result["release_authorized"])
            self.assertEqual(result["next_action"], "final-report")
            self.assertTrue((output / "summary-v2.json").is_file())
            summary = json.loads((output / "summary-v2.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["schema_version"], "ds-lite.autonomy-summary.v2")
            self.assertEqual(summary["work_unit_ref"], "research/work-unit.json")
            self.assertEqual(summary["gate_ids"], ["gate-a"])
            self.assertEqual(summary["authorization_ref"], "approvals/user.md")
            (root / "research" / "autonomy" / "stop-first.json").write_text(json.dumps({
                "schema_version": "ds-lite.stop-first-protocol.v1", "status": "prepared",
            }), encoding="utf-8")
            self.assertEqual(ds_lite_hook._autonomy_stop_gaps(root), [])

    def test_hook_rejects_summary_binding_drift(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            contract_path = root / "research" / "autonomy" / "contract.json"
            run = contract_path.parent / "run"
            contract_path.parent.mkdir(parents=True, exist_ok=True)
            (root / "research" / "work-unit.json").write_text("{}", encoding="utf-8")
            contract_path.write_text(json.dumps(self.contract(root)), encoding="utf-8")
            run.mkdir()
            summary = ds_lite_autonomy_v2.summarize(
                self.contract(root), status="completed", completed=["gate-a"], blocked=[], next_action="final-report"
            )
            summary["gate_ids"] = ["other-gate"]
            (run / "summary-v2.json").write_text(json.dumps(summary), encoding="utf-8")
            (run / "progress-001.json").write_text(json.dumps({"status": "completed"}), encoding="utf-8")
            self.assertEqual(
                ds_lite_hook._autonomy_stop_gaps(root),
                ["autonomy v2 summary gate_ids does not match contract"],
            )

    def test_legacy_execution_projection_fails_closed_on_goal_drift(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            value = self.contract(root, execution={
                "contract": {
                    "schema_version": "ds-lite.autonomy-contract.v1",
                    "goals": ["different-goal"],
                    "budget": {"max_seconds": 60, "max_attempts_per_gate": 3},
                    "authorization": {"status": "approved", "authority": "user", "ref": "approvals/user.md"},
                    "gates": [{
                        "id": "gate-a", "depends_on": [], "command": ["echo", "ok"],
                        "receipt_ref": "receipts/gate-a.json", "retry_class": "none",
                    }],
                }
            })
            normalized = ds_lite_autonomy_v2.validate_contract(value, project_root=root)
            with self.assertRaisesRegex(ds_lite_autonomy_v2.AutonomyV2Error, "goals"):
                ds_lite_autonomy_v2._execution_map(normalized)


if __name__ == "__main__":
    unittest.main()
