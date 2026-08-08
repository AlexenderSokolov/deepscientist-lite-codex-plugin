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
        work.parent.mkdir(parents=True)
        work.write_text("{}", encoding="utf-8")
        value = {
            "schema_version": "ds-lite.autonomy-contract.v2",
            "work_unit_ref": "research/work-unit.json",
            "goals": ["verify-core"],
            "gates": [{"id": "gate-a", "depends_on": []}],
            "budget": {"max_seconds": 60},
            "authorization": {"status": "approved", "scope": "project", "release_gate": False},
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
                "contract": {
                    "autonomy_id": "v2-success",
                    "status": "prepared",
                    "goals": ["verify-core"],
                    "budget": {"max_attempts_per_gate": 3, "max_seconds": 30},
                    "authorization": {"status": "approved", "authority": "user", "ref": "approvals/user.md"},
                    "release": {"authorized": True, "required_gates": ["gate-a"]},
                    "gates": [{
                        "id": "gate-a",
                        "depends_on": [],
                        "command": [sys.executable, "runner.py", "receipts/gate-a-{attempt}.json"],
                        "receipt_ref": "receipts/gate-a-{attempt}.json",
                        "retry_class": "none",
                    }],
                }
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
            self.assertEqual(json.loads((output / "summary-v2.json").read_text(encoding="utf-8"))["schema_version"], "ds-lite.autonomy-summary.v2")
            (root / "research" / "autonomy" / "stop-first.json").write_text(json.dumps({
                "schema_version": "ds-lite.stop-first-protocol.v1", "status": "prepared",
            }), encoding="utf-8")
            self.assertEqual(ds_lite_hook._autonomy_stop_gaps(root), [])


if __name__ == "__main__":
    unittest.main()
