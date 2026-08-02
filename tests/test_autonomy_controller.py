from __future__ import annotations

import json
import os
import sys
import unittest
import uuid
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from plugins.deepscientist_lite_import_shim import ds_lite_autonomy


class AutonomyControllerTests(unittest.TestCase):
    def setUp(self) -> None:
        writable_root = Path(os.environ.get("DS_LITE_TEST_ROOT", ROOT / ".tmp-test-artifacts"))
        self.root = writable_root / f"ds-lite-autonomy-{uuid.uuid4().hex[:12]}"
        self.root.mkdir(parents=True, exist_ok=False)
        (self.root / "receipts").mkdir()
        (self.root / "runner.py").write_text(
            "import json, pathlib, sys\n"
            "out = pathlib.Path(sys.argv[1])\n"
            "out.write_text(json.dumps({'status': 'passed'}), encoding='utf-8')\n",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        # Preserve isolated receipts for post-test inspection.
        pass

    def contract(self, gates: list[dict[str, object]]) -> dict[str, object]:
        return {
            "schema_version": "ds-lite.autonomy-contract.v1",
            "autonomy_id": "release-081",
            "status": "prepared",
            "goals": ["release-gate"],
            "gates": gates,
            "budget": {"max_attempts_per_gate": 3, "max_seconds": 60},
            "authorization": {"status": "approved", "authority": "user", "ref": "approvals/user.md"},
            "release": {"authorized": True, "required_gates": [item["id"] for item in gates]},
        }

    def write_contract(self, value: dict[str, object]) -> Path:
        (self.root / "approvals").mkdir(exist_ok=True)
        (self.root / "approvals" / "user.md").write_text("approved\n", encoding="utf-8")
        path = self.root / "contract.json"
        path.write_text(json.dumps(value), encoding="utf-8")
        return path

    def test_runs_ready_gates_then_dependents_and_writes_progress(self) -> None:
        gates = [
            {"id": "source", "depends_on": [], "command": [sys.executable, "runner.py", "receipts/source-{attempt}.json"], "receipt_ref": "receipts/source-{attempt}.json", "retry_class": "none"},
            {"id": "release", "depends_on": ["source"], "command": [sys.executable, "runner.py", "receipts/release-{attempt}.json"], "receipt_ref": "receipts/release-{attempt}.json", "retry_class": "none"},
        ]
        summary = ds_lite_autonomy.run(self.root, self.write_contract(self.contract(gates)), self.root / "run")
        self.assertEqual(summary["status"], "completed")
        self.assertEqual(summary["completed_gates"], ["release", "source"])
        progress = sorted((self.root / "run").glob("progress-*.json"))
        self.assertEqual(len(progress), 2)
        self.assertEqual(json.loads(progress[-1].read_text(encoding="utf-8"))["next_action"], "final-report")
        heartbeat_lines = (self.root / "run" / "heartbeat.jsonl").read_text(encoding="utf-8").splitlines()
        self.assertGreaterEqual(len(heartbeat_lines), 2)
        heartbeat = json.loads(heartbeat_lines[0])
        self.assertEqual(heartbeat["report_due_seconds"], 60)
        self.assertEqual(heartbeat["frozen_goals"], ["release-gate"])
        self.assertFalse(heartbeat["raw_output_persisted"])
        self.assertEqual(set(summary["gates"]["source"]), {
            "status", "failure_layer", "attempts", "automatic_retry_observed",
            "automatic_fresh_continuation_observed", "frozen_attempt", "evidence_ref",
            "receipt_ref", "quiet_receipt_polls", "next_automatic_action", "recovery",
        })

    def test_retries_only_transient_gate_up_to_three_attempts(self) -> None:
        (self.root / "flaky.py").write_text(
            "import json, pathlib, sys\n"
            "count = pathlib.Path('count.txt')\n"
            "n = int(count.read_text()) + 1 if count.exists() else 1\n"
            "count.write_text(str(n))\n"
            "out = pathlib.Path(sys.argv[1])\n"
            "out.write_text(json.dumps({'status': 'passed' if n == 3 else 'blocked', 'failure_layer': 'network'}))\n"
            "raise SystemExit(0 if n == 3 else 1)\n",
            encoding="utf-8",
        )
        gates = [{"id": "provider", "depends_on": [], "command": [sys.executable, "flaky.py", "receipts/provider-{attempt}.json"], "receipt_ref": "receipts/provider-{attempt}.json", "retry_class": "transient"}]
        summary = ds_lite_autonomy.run(self.root, self.write_contract(self.contract(gates)), self.root / "run")
        self.assertEqual(summary["status"], "completed")
        self.assertEqual((self.root / "count.txt").read_text(encoding="utf-8"), "3")
        gate = summary["gates"]["provider"]
        self.assertEqual(gate["attempts"], 3)
        self.assertTrue(gate["automatic_retry_observed"])

    def test_non_retryable_failure_freezes_gate_without_replacement(self) -> None:
        (self.root / "fail.py").write_text(
            "import json, pathlib\n"
            "pathlib.Path('receipts/fail.json').write_text(json.dumps({'status': 'blocked', 'failure_layer': 'duplicate-risk'}))\n"
            "raise SystemExit(1)\n",
            encoding="utf-8",
        )
        gates = [{"id": "publish", "depends_on": [], "command": [sys.executable, "fail.py"], "receipt_ref": "receipts/fail.json", "retry_class": "none"}]
        summary = ds_lite_autonomy.run(self.root, self.write_contract(self.contract(gates)), self.root / "run")
        self.assertEqual(summary["status"], "blocked")
        self.assertEqual(summary["gates"]["publish"]["attempts"], 1)

    def test_blocked_gate_does_not_prevent_independent_gate_from_running(self) -> None:
        (self.root / "fail.py").write_text(
            "import json, pathlib\n"
            "pathlib.Path('receipts/frozen.json').write_text(json.dumps({'status': 'blocked', 'failure_layer': 'duplicate-risk'}))\n"
            "raise SystemExit(1)\n",
            encoding="utf-8",
        )
        gates = [
            {"id": "matched-effect", "depends_on": [], "command": [sys.executable, "fail.py"], "receipt_ref": "receipts/frozen.json", "retry_class": "none"},
            {"id": "web", "depends_on": [], "command": [sys.executable, "runner.py", "receipts/web-1.json"], "receipt_ref": "receipts/web-1.json", "retry_class": "none"},
        ]
        summary = ds_lite_autonomy.run(self.root, self.write_contract(self.contract(gates)), self.root / "run")
        self.assertEqual(summary["status"], "blocked")
        self.assertEqual(summary["gates"]["matched-effect"]["status"], "awaiting_user_action")
        self.assertEqual(summary["awaiting_user_action_gates"], ["matched-effect"])
        self.assertEqual(summary["gates"]["web"]["status"], "passed")
        self.assertEqual(summary["completed_gates"], ["web"])

    def test_dependency_blocked_gate_gets_terminal_progress_receipt(self) -> None:
        gates = [
            {"id": "provider", "depends_on": [], "command": [sys.executable, "fail.py"], "receipt_ref": "receipts/provider.json", "retry_class": "none"},
            {"id": "release", "depends_on": ["provider"], "command": [sys.executable, "runner.py", "receipts/release.json"], "receipt_ref": "receipts/release.json", "retry_class": "none"},
        ]
        (self.root / "fail.py").write_text(
            "import json, pathlib\n"
            "pathlib.Path('receipts/provider.json').write_text(json.dumps({'status': 'blocked', 'failure_layer': 'duplicate-risk'}))\n"
            "raise SystemExit(1)\n",
            encoding="utf-8",
        )
        summary = ds_lite_autonomy.run(self.root, self.write_contract(self.contract(gates)), self.root / "run")
        self.assertEqual(summary["gates"]["release"]["failure_layer"], "dependency-blocked")
        self.assertTrue(any(json.loads(path.read_text(encoding="utf-8")).get("active_gate") == "release" for path in (self.root / "run").glob("progress-*.json")))

    def test_approved_fresh_continuation_preserves_frozen_receipt_then_advances(self) -> None:
        (self.root / "fail.py").write_text(
            "import json, pathlib\n"
            "pathlib.Path('receipts/frozen-0.json').write_text(json.dumps({'status': 'blocked', 'failure_layer': 'transport'}))\n"
            "raise SystemExit(1)\n",
            encoding="utf-8",
        )
        gates = [{
            "id": "provider", "depends_on": [], "command": [sys.executable, "fail.py"],
            "receipt_ref": "receipts/frozen-{continuation}.json", "retry_class": "none",
            "continuation_command": [sys.executable, "runner.py", "receipts/fresh-{continuation}.json"],
            "continuation_receipt_ref": "receipts/fresh-{continuation}.json",
        }]
        summary = ds_lite_autonomy.run(self.root, self.write_contract(self.contract(gates)), self.root / "run")
        self.assertEqual(summary["status"], "completed")
        self.assertTrue((self.root / "receipts" / "frozen-0.json").is_file())
        self.assertTrue((self.root / "receipts" / "fresh-1.json").is_file())
        result = summary["gates"]["provider"]
        self.assertTrue(result["automatic_fresh_continuation_observed"])
        self.assertEqual(result["frozen_attempt"]["receipt_ref"], "receipts/frozen-0.json")

    def test_continuity_allows_up_to_six_transient_attempts(self) -> None:
        (self.root / "flaky.py").write_text(
            "import json, pathlib, sys\n"
            "count = pathlib.Path('count.txt')\n"
            "n = int(count.read_text()) + 1 if count.exists() else 1\n"
            "count.write_text(str(n))\n"
            "out = pathlib.Path(sys.argv[1])\n"
            "out.write_text(json.dumps({'status': 'passed' if n == 6 else 'blocked', 'failure_layer': 'network'}))\n"
            "raise SystemExit(0 if n == 6 else 1)\n",
            encoding="utf-8",
        )
        contract = self.contract([{"id": "provider", "depends_on": [], "command": [sys.executable, "flaky.py", "receipts/provider-{attempt}.json"], "receipt_ref": "receipts/provider-{attempt}.json", "retry_class": "transient"}])
        contract["budget"] = {"max_attempts_per_gate": 6, "max_seconds": 60}
        contract["continuity"] = {"quiet_receipt_polls": 3, "quiet_poll_seconds": 0, "retry_delays_seconds": [0, 0, 0, 0, 0]}
        summary = ds_lite_autonomy.run(self.root, self.write_contract(contract), self.root / "run")
        self.assertEqual(summary["status"], "completed")
        self.assertEqual(summary["gates"]["provider"]["attempts"], 6)

    def test_silent_receipt_polling_records_delayed_terminal_receipt(self) -> None:
        gates = [{"id": "source", "depends_on": [], "command": [sys.executable, "runner.py", "receipts/source-1.json"], "receipt_ref": "receipts/source-1.json", "retry_class": "none"}]
        contract = self.contract(gates)
        contract["continuity"] = {"quiet_receipt_polls": 2, "quiet_poll_seconds": 0, "retry_delays_seconds": [0, 0]}
        states = [("not-observed", "receipt-missing"), ("not-observed", "receipt-missing"), ("passed", "none")]
        with mock.patch.object(ds_lite_autonomy, "_load_receipt", side_effect=states):
            summary = ds_lite_autonomy.run(self.root, self.write_contract(contract), self.root / "run")
        self.assertEqual(summary["status"], "completed")
        self.assertEqual(summary["gates"]["source"]["quiet_receipt_polls"], 2)

    def test_resume_runs_only_the_remaining_gate_after_interruption(self) -> None:
        gates = [
            {"id": "source", "depends_on": [], "command": [sys.executable, "runner.py", "receipts/source-1.json"], "receipt_ref": "receipts/source-1.json", "retry_class": "none"},
            {"id": "release", "depends_on": ["source"], "command": [sys.executable, "runner.py", "receipts/release-1.json"], "receipt_ref": "receipts/release-1.json", "retry_class": "none"},
        ]
        contract = self.contract(gates)
        path = self.write_contract(contract)
        output = self.root / "run"
        output.mkdir()
        payload = ds_lite_autonomy._progress(contract, 1, "source", "passed", ["source"], [], "run-next-ready-gate", failure_layer="none", attempts=1, receipt_ref="receipts/source-1.json", quiet_polls=0)
        (output / "progress-001.json").write_text(json.dumps(payload), encoding="utf-8")
        summary = ds_lite_autonomy.run(self.root, path, output, resume=True)
        self.assertEqual(summary["status"], "completed")
        self.assertEqual(summary["completed_gates"], ["release", "source"])
        self.assertTrue((self.root / "receipts" / "release-1.json").is_file())

    def test_resume_retries_transient_gate_from_blocked_summary(self) -> None:
        gate = {
            "id": "provider",
            "depends_on": [],
            "command": [sys.executable, "runner.py", "receipts/provider-1.json"],
            "receipt_ref": "receipts/provider-1.json",
            "retry_class": "transient",
        }
        contract = self.contract([gate])
        path = self.write_contract(contract)
        output = self.root / "run"
        output.mkdir()
        (output / "summary.json").write_text(json.dumps({
            "schema_version": "ds-lite.autonomy-summary.v1",
            "autonomy_id": "release-081",
            "status": "blocked",
            "completed_gates": [],
            "blocked_gates": ["provider"],
            "awaiting_user_action_gates": [],
            "gates": {
                "provider": {
                    "status": "blocked",
                    "failure_layer": "network",
                    "attempts": 1,
                    "automatic_retry_observed": False,
                    "receipt_ref": "receipts/provider-0.json",
                }
            },
        }), encoding="utf-8")
        summary = ds_lite_autonomy.run(self.root, path, output, resume=True)
        self.assertEqual(summary["status"], "completed")
        self.assertTrue((self.root / "receipts" / "provider-1.json").is_file())
        self.assertTrue((output / "summary.json").is_file())
        rotated = output / summary["summary_ref"]
        self.assertTrue(rotated.is_file())
        self.assertNotEqual(rotated.name, "summary.json")
        self.assertEqual(json.loads((output / "summary.json").read_text(encoding="utf-8"))["status"], "blocked")

    def test_resume_summary_rotation_keeps_each_completed_snapshot(self) -> None:
        gate = {
            "id": "provider",
            "depends_on": [],
            "command": [sys.executable, "runner.py", "receipts/provider-{attempt}.json"],
            "receipt_ref": "receipts/provider-{attempt}.json",
            "retry_class": "transient",
        }
        contract = self.contract([gate])
        path = self.write_contract(contract)
        output = self.root / "run"
        output.mkdir()
        blocked = {
            "schema_version": "ds-lite.autonomy-summary.v1",
            "autonomy_id": "release-081",
            "status": "blocked",
            "completed_gates": [],
            "blocked_gates": ["provider"],
            "awaiting_user_action_gates": [],
            "gates": {"provider": {"status": "blocked", "failure_layer": "network", "attempts": 1}},
        }
        (output / "summary.json").write_text(json.dumps(blocked), encoding="utf-8")
        first = ds_lite_autonomy.run(self.root, path, output, resume=True)
        self.assertEqual(first["status"], "completed")
        first_ref = first["summary_ref"]
        second = ds_lite_autonomy.run(self.root, path, output, resume=True)
        self.assertEqual(second["status"], "completed")
        self.assertEqual(second["summary_ref"], first_ref)
        self.assertTrue((output / first_ref).is_file())
        self.assertEqual(len(list(output.glob("summary-resume-*.json"))), 1)


if __name__ == "__main__":
    unittest.main()
