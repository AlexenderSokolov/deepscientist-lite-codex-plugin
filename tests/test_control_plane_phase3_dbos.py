from __future__ import annotations

import sys
import tempfile
import unittest
import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTROLLER_ROOT = ROOT / "plugins" / "deepscientist-lite-core" / "controller"
sys.path.insert(0, str(CONTROLLER_ROOT))

from ds_lite_control.dbos_bridge import DBOSBridge, PHASE3_WORKFLOW_NAMES
from ds_lite_control.failure_policy import FailureClassifier
from ds_lite_control.scheduler import DagScheduler
from ds_lite_control.store import ControlStore


class Phase3DbosTests(unittest.TestCase):
    def test_real_dbos_cooldown_uses_action_identity_and_wakes_one_gate(self) -> None:
        if importlib.util.find_spec("dbos") is None:
            self.skipTest("DBOS optional dependency is not installed")
        with tempfile.TemporaryDirectory(prefix="ds-lite-phase3-dbos-") as directory:
            root = Path(directory)
            store = ControlStore(root / "control.sqlite3")
            bridge = None
            try:
                scheduler = DagScheduler(store, FailureClassifier(seed=1))
                scheduler.register_job(
                    "job-1",
                    [{"id": "gate-a", "type": "analysis"}, {"id": "gate-b", "type": "analysis"}],
                    [],
                )
                claims = scheduler.claim_ready("job-1", "owner-1")
                by_id = {claim.work_item_id: claim for claim in claims}
                for claim in claims:
                    scheduler.record_failure(
                        claim, layer="provider", http_status=429,
                        retry_after_seconds=0, evidence_hash=claim.work_item_id.encode().hex().ljust(64, "0"),
                    )
                bridge = DBOSBridge(root / "runtime.sqlite3")
                handle = bridge.start_cooldown(
                    by_id["gate-a"].action_id, "gate-a", root / "control.sqlite3",
                    "owner-1", by_id["gate-a"].fence_epoch, delay_seconds=0,
                )
                result = handle.get_result()
                self.assertEqual(handle.workflow_id, by_id["gate-a"].action_id)
                self.assertEqual(result["terminal_status"], "ready")
                self.assertEqual(store.work_item("gate-a")["state"], "pending")
                self.assertEqual(store.work_item("gate-b")["state"], "cooldown")
            finally:
                if bridge is not None:
                    bridge.close()
                store.close()

    def test_phase3_registry_is_additive(self) -> None:
        self.assertEqual(
            PHASE3_WORKFLOW_NAMES,
            (
                "reconcile_job_v1", "run_action_v1", "project_status_v1",
                "run_codex_action_v1", "schedule_job_v1", "cooldown_gate_v1",
                "reconcile_gate_v1",
            ),
        )


if __name__ == "__main__":
    unittest.main()
