import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTROLLER_ROOT = ROOT / "plugins" / "deepscientist-lite-core" / "controller"
SCHEMA_ROOT = ROOT / "plugins" / "deepscientist-lite-core" / "schemas" / "codex" / "0.128.0"
sys.path.insert(0, str(CONTROLLER_ROOT))

from ds_lite_control.app_server import AppServerResponseTimeout, AppServerAdapter
from ds_lite_control.codex_actions import CodexActionRunner
from ds_lite_control.domain import ControlStore, FenceRejected
from ds_lite_control.workflows import WORKFLOW_REGISTRY
from support_fake_process import FakeProcess


class Phase2RunnerTests(unittest.TestCase):
    def test_codex_workflow_is_versioned_without_redefining_phase1_workflow(self):
        self.assertEqual(WORKFLOW_REGISTRY["run_action_v1"]["version"], 1)
        self.assertEqual(WORKFLOW_REGISTRY["run_codex_action_v1"]["version"], 1)
    def setUp(self):
        self.temporary = self._temporary = __import__("tempfile").TemporaryDirectory(prefix="ds-lite-runner-")
        self.root = Path(self.temporary.name)
        self.store = ControlStore(self.root / "control.sqlite3")
        self.epoch = self.store.create_job_work_item("job-1", "work-1", "owner-1")
        self.store.plan_attempt_action(
            job_id="job-1", work_item_id="work-1", attempt_id="attempt-1",
            action_id="action-1", kind="codex-turn", payload_hash="a" * 64,
            owner_id="owner-1", fence_epoch=self.epoch,
        )
        self.store.bind_canonical_thread(
            "attempt-1", "codex-app-server", "thread-1", "schema", "owner-1", self.epoch,
        )

    def tearDown(self):
        self.store.close()
        self.temporary.cleanup()

    def test_duplicate_action_reuses_acknowledged_request_without_second_turn_start(self):
        def on_write(message):
            if message["method"] == "turn/start":
                process.emit({"id": message["id"], "result": {"turn": {"id": "turn-1"}}})

        process = FakeProcess(on_write)
        adapter = AppServerAdapter(process, SCHEMA_ROOT, response_timeout=1)
        runner = CodexActionRunner(self.store, adapter)
        first = runner.dispatch_turn(
            "action-1", "attempt-1", [{"type": "text", "text": "OK"}], "owner-1", self.epoch,
        )
        second = runner.dispatch_turn(
            "action-1", "attempt-1", [{"type": "text", "text": "OK"}], "owner-1", self.epoch,
        )
        self.assertEqual(first.disposition, "acknowledged")
        self.assertEqual(second.disposition, "acknowledged")
        self.assertEqual([row["method"] for row in process.writes], ["turn/start"])
        self.assertEqual(self.store.rpc_request("action-1:turn-start")["state"], "acknowledged")

    def test_response_loss_freezes_ambiguous_and_does_not_retry(self):
        def on_write(message):
            if message["method"] == "turn/start":
                process.emit({"method": "turn/started", "params": {
                    "threadId": "thread-1", "turn": {"id": "turn-1", "status": "inProgress"},
                }})

        process = FakeProcess(on_write)
        adapter = AppServerAdapter(process, SCHEMA_ROOT, response_timeout=0.05)
        runner = CodexActionRunner(self.store, adapter)
        first = runner.dispatch_turn(
            "action-1", "attempt-1", [{"type": "text", "text": "OK"}], "owner-1", self.epoch,
        )
        second = runner.dispatch_turn(
            "action-1", "attempt-1", [{"type": "text", "text": "OK"}], "owner-1", self.epoch,
        )
        self.assertEqual(first.disposition, "ambiguous")
        self.assertEqual(second.disposition, "ambiguous")
        self.assertEqual([row["method"] for row in process.writes], ["turn/start"])

    def test_stale_fence_is_rejected_before_any_host_write(self):
        process = FakeProcess(lambda message: None)
        adapter = AppServerAdapter(process, SCHEMA_ROOT, response_timeout=1)
        runner = CodexActionRunner(self.store, adapter)
        self.store.acquire_lease(
            "work-1", "owner-2", allow_unexpired_takeover=True
        )
        with self.assertRaises(FenceRejected):
            runner.dispatch_turn(
                "action-1", "attempt-1", [{"type": "text", "text": "OK"}], "owner-1", self.epoch,
            )
        self.assertEqual(process.writes, [])


if __name__ == "__main__":
    unittest.main()
