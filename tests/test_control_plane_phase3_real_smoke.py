from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from teaching.controller_phase3_multigate_smoke import (
    record_terminal_failure,
    evaluate_records,
    reconcile_dropped_turn_identity,
    select_requested_model,
)
from ds_lite_control.app_server import RpcObservation
from ds_lite_control.failure_policy import FailureClassifier
from ds_lite_control.scheduler import DagScheduler
from ds_lite_control.store import ControlStore


class Phase3RealSmokeDecisionTests(unittest.TestCase):
    def test_real_provider_terminal_failure_is_gate_local_cooldown(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = ControlStore(Path(directory) / "control.sqlite3")
            try:
                scheduler = DagScheduler(store, FailureClassifier(seed=20260731))
                scheduler.register_job("job", [
                    {"id": "gate-a", "type": "experiment", "priority": 2},
                    {"id": "gate-b", "type": "analysis", "priority": 1},
                ], [])
                claims = {claim.work_item_id: claim for claim in scheduler.claim_ready("job", "owner")}
                result = record_terminal_failure(
                    store, claims["gate-a"],
                    RpcObservation("turn/observe", "request", 1, None, "thread", "turn", "failed"),
                )
                self.assertEqual(result["disposition"], "cooldown")
                self.assertEqual(store.work_item("gate-a")["state"], "cooldown")
                self.assertEqual(store.work_item("gate-b")["state"], "running")
            finally:
                store.close()

    def test_requested_model_must_be_visible_in_real_catalog(self) -> None:
        catalog = [
            {"model": "gpt-current", "hidden": False},
            {"model": "hidden-model", "hidden": True},
        ]
        self.assertEqual(select_requested_model(catalog, "gpt-current"), "gpt-current")
        with self.assertRaises(RuntimeError):
            select_requested_model(catalog, "hidden-model")
        with self.assertRaises(RuntimeError):
            select_requested_model(catalog, "missing")

    def records(self):
        return {
            "gate_a_drop": {
                "action_id": "phase3-real-gate-a:action:1",
                "thread_id": "thread-a", "turn_id": "turn-a",
                "disposition": "ambiguous", "controller_pid": 101,
                "app_server_pid": 900, "owner_id": "owner-a", "fence_epoch": 1,
            },
            "gate_b": {
                "action_id": "phase3-real-gate-b:action:1",
                "thread_id": "thread-b", "turn_id": "turn-b",
                "disposition": "terminal", "controller_pid": 102,
                "app_server_pid": 900, "owner_id": "owner-b", "fence_epoch": 1,
            },
            "gate_a_recover": {
                "action_id": "phase3-real-gate-a:action:1",
                "thread_id": "thread-a", "turn_id": "turn-a",
                "disposition": "terminal", "controller_pid": 103,
                "app_server_pid": 900, "owner_id": "owner-c", "fence_epoch": 2,
            },
        }

    def test_distinct_threads_single_dispatch_and_single_side_effect_pass(self) -> None:
        result = evaluate_records(
            self.records(), turn_start_count=2, dropped_response_count=1,
            side_effect_count=1,
        )
        self.assertTrue(result["passed"])
        self.assertTrue(all(result["checks"].values()))

    def test_same_owner_or_fence_does_not_prove_ttl_takeover(self) -> None:
        records = self.records()
        records["gate_a_recover"]["owner_id"] = "owner-a"
        records["gate_a_recover"]["fence_epoch"] = 1
        result = evaluate_records(
            records, turn_start_count=2, dropped_response_count=1,
            side_effect_count=1,
        )
        self.assertFalse(result["passed"])
        self.assertFalse(result["checks"]["ttl_owner_takeover"])

    def test_dropped_response_turn_is_recovered_from_matching_request(self) -> None:
        records = self.records()
        records["gate_a_drop"]["turn_id"] = None
        rows = [{
            "direction": "inbound",
            "request_id": "phase3-real-gate-a:action:1:turn-start",
            "turn_id": "turn-a",
            "host_observed": True,
        }]
        reconciled = reconcile_dropped_turn_identity(records, rows)
        self.assertEqual(reconciled["gate_a_drop"]["turn_id"], "turn-a")

    def test_conflicting_host_turn_identity_fails_closed(self) -> None:
        records = self.records()
        records["gate_a_drop"]["turn_id"] = None
        rows = [{
            "direction": "inbound",
            "request_id": "phase3-real-gate-a:action:1:turn-start",
            "turn_id": "different-turn",
            "host_observed": True,
        }]
        with self.assertRaises(RuntimeError):
            reconcile_dropped_turn_identity(records, rows)

    def test_duplicate_dispatch_same_thread_or_duplicate_effect_fails(self) -> None:
        for mutation in ("duplicate-turn", "same-thread", "duplicate-effect"):
            with self.subTest(mutation=mutation):
                records = self.records()
                turns = 2
                effects = 1
                if mutation == "duplicate-turn":
                    turns = 3
                elif mutation == "same-thread":
                    records["gate_b"]["thread_id"] = "thread-a"
                else:
                    effects = 2
                result = evaluate_records(
                    records, turn_start_count=turns, dropped_response_count=1,
                    side_effect_count=effects,
                )
                self.assertFalse(result["passed"])


if __name__ == "__main__":
    unittest.main()
