from __future__ import annotations

import tempfile
import sys
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTROLLER_ROOT = ROOT / "plugins" / "deepscientist-lite-core" / "controller"
import sys

sys.path.insert(0, str(CONTROLLER_ROOT))

from ds_lite_control.errors import FenceRejected, IntegrityIncident, LeaseBusy
from ds_lite_control.dbos_bridge import _cooldown_gate_body
from ds_lite_control.backup import backup_control_plane, restore_control_plane, verify_backup
from ds_lite_control.failure_policy import FailureClassifier
from ds_lite_control.scheduler import DagScheduler
from ds_lite_control.store import ControlStore
from ds_lite_control.supervisor import RepoSupervisor, render_service_template
from ds_lite_control.workflows import WORKFLOW_REGISTRY


class MutableClock:
    def __init__(self, value: datetime) -> None:
        self.value = value

    def __call__(self) -> datetime:
        return self.value


class Phase3MigrationAndLeaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="ds-lite-phase3-")
        self.root = Path(self.temporary.name)
        self.clock = MutableClock(datetime(2026, 7, 31, 0, 0, tzinfo=timezone.utc))

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_new_database_uses_schema_v3(self) -> None:
        store = ControlStore(self.root / "control.sqlite3", clock=self.clock)
        try:
            self.assertEqual(store.schema_version, 4)
            tables = {
                row[0]
                for row in store.connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            self.assertTrue(
                {"scheduler_runs", "gate_results", "handoffs", "supervisor_heartbeats"}
                <= tables
            )
        finally:
            store.close()

    def test_new_owner_waits_for_lease_expiry_and_old_owner_is_fenced(self) -> None:
        store = ControlStore(self.root / "control.sqlite3", clock=self.clock)
        try:
            old_epoch = store.create_job_work_item(
                "job-1", "gate-a", "owner-a", lease_ttl_seconds=60
            )
            with self.assertRaises(LeaseBusy):
                store.acquire_lease("gate-a", "owner-b", ttl_seconds=60)

            self.clock.value += timedelta(seconds=61)
            new_epoch = store.acquire_lease("gate-a", "owner-b", ttl_seconds=60)
            self.assertEqual(new_epoch, old_epoch + 1)
            with self.assertRaises(FenceRejected):
                store.heartbeat_lease("gate-a", "owner-a", old_epoch, ttl_seconds=60)
            store.heartbeat_lease("gate-a", "owner-b", new_epoch, ttl_seconds=60)
        finally:
            store.close()


class FailureClassifierTests(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime(2026, 7, 31, 0, 0, tzinfo=timezone.utc)
        self.classifier = FailureClassifier(seed=20260731)

    def test_rate_limit_honors_retry_after(self) -> None:
        decision = self.classifier.classify(
            layer="provider", http_status=429, retry_after_seconds=45,
            attempt=1, now=self.now,
        )
        self.assertEqual(decision.failure_class, "rate-limit")
        self.assertEqual(decision.disposition, "cooldown")
        self.assertEqual(decision.retry_delay_seconds, 45)
        self.assertEqual(decision.next_eligible_at, "2026-07-31T00:00:45Z")

    def test_auth_and_trust_never_retry_network(self) -> None:
        for layer in ("auth", "hook-trust", "permission"):
            with self.subTest(layer=layer):
                decision = self.classifier.classify(layer=layer, attempt=1, now=self.now)
                self.assertEqual(decision.disposition, "awaiting_user_action")
                self.assertEqual(decision.retry_delay_seconds, 0)
                self.assertEqual(decision.next_action, "await-user-action")

    def test_ambiguous_reconciles_and_negative_is_scientific_terminal(self) -> None:
        ambiguous = self.classifier.classify(
            layer="ambiguous-transport", attempt=1, now=self.now
        )
        self.assertEqual(ambiguous.disposition, "reconciling")
        self.assertEqual(ambiguous.next_action, "reconcile-same-identity")

        negative = self.classifier.classify(
            layer="scientific-negative", attempt=1, now=self.now
        )
        self.assertEqual(negative.disposition, "valid_negative")
        self.assertEqual(negative.failure_class, "scientific-result")
        self.assertEqual(negative.next_action, "create-next-iteration")


class RepoSupervisorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="ds-lite-supervisor-")
        self.root = Path(self.temporary.name)
        self.store = ControlStore(self.root / "control.sqlite3")

    def tearDown(self) -> None:
        self.store.close()
        self.temporary.cleanup()

    def test_real_child_is_started_restarted_and_stopped_by_request(self) -> None:
        supervisor = RepoSupervisor(
            self.store,
            runtime_root=self.root / "runtime",
            supervisor_id="supervisor-1",
            owner_id="owner-1",
            worker_command=[sys.executable, "-c", "raise SystemExit(7)"],
            heartbeat_ttl_seconds=60,
        )
        first = supervisor.tick()
        self.assertEqual(first["generation"], 1)
        time.sleep(0.2)
        second = supervisor.tick()
        self.assertEqual(second["generation"], 2)
        self.assertEqual(second["last_exit_code"], 7)

        supervisor.request_stop()
        stopped = supervisor.tick()
        self.assertEqual(stopped["state"], "stopped")
        heartbeat = self.store.connection.execute(
            "SELECT state FROM supervisor_heartbeats WHERE supervisor_id='supervisor-1'"
        ).fetchone()
        self.assertEqual(heartbeat[0], "stopped")

    def test_service_templates_are_review_only_and_exclusive_create(self) -> None:
        windows = self.root / "windows-task.xml"
        systemd = self.root / "ds-lite-control.service"
        render_service_template(
            "windows", windows, project=self.root, python_bin=Path(sys.executable)
        )
        render_service_template(
            "systemd", systemd, project=self.root, python_bin=Path(sys.executable)
        )
        self.assertIn("ds_lite_control supervisor run", windows.read_text(encoding="utf-8"))
        self.assertIn("ExecStart=", systemd.read_text(encoding="utf-8"))
        with self.assertRaises(FileExistsError):
            render_service_template(
                "windows", windows, project=self.root, python_bin=Path(sys.executable)
            )


class Phase3BackupTests(unittest.TestCase):
    def test_v4_backup_requires_and_restores_supervisor_witness(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ds-lite-phase3-backup-") as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            store = ControlStore(source / "control.sqlite3")
            try:
                store.record_supervisor_heartbeat(
                    "supervisor-1", "owner-1", controller_pid=123,
                    witness_hash="a" * 64,
                )
            finally:
                store.close()
            import sqlite3
            sqlite3.connect(source / "runtime.sqlite3").close()
            (source / "receipts").mkdir()
            (source / "receipts" / "one.json").write_text("{}\n", encoding="utf-8")
            (source / "supervisor").mkdir()
            (source / "supervisor" / "supervisor-state.json").write_text(
                '{"state":"active"}\n', encoding="utf-8"
            )

            backup = root / "backup"
            manifest = backup_control_plane(
                source, backup, require_supervisor=True
            )
            self.assertEqual(manifest["schema_version"], "ds-lite.control-backup.v4")
            self.assertTrue(verify_backup(backup)["valid"])
            restored = root / "restored"
            result = restore_control_plane(backup, restored)
            self.assertTrue(result["valid"])
            self.assertTrue((restored / "supervisor" / "supervisor-state.json").is_file())

            incomplete = root / "incomplete"
            incomplete.mkdir()
            with self.assertRaises(FileNotFoundError):
                backup_control_plane(incomplete, root / "never", require_supervisor=True)


class DagSchedulerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="ds-lite-scheduler-")
        self.root = Path(self.temporary.name)
        self.clock = MutableClock(datetime(2026, 7, 31, 1, 0, tzinfo=timezone.utc))
        self.store = ControlStore(self.root / "control.sqlite3", clock=self.clock)
        self.scheduler = DagScheduler(
            self.store,
            FailureClassifier(seed=20260731),
            clock=self.clock,
            max_concurrency=2,
            retry_concurrency=1,
        )

    def test_expired_running_claim_is_recovered_without_new_action(self) -> None:
        scheduler = DagScheduler(
            self.store, FailureClassifier(seed=20260731), clock=self.clock,
            max_concurrency=2, retry_concurrency=1, lease_ttl_seconds=5,
        )
        scheduler.register_job(
            "recover-job", [{"id": "gate-a", "type": "analysis"}], [],
        )
        original = scheduler.claim_ready("recover-job", "owner-a")[0]
        self.clock.value += timedelta(seconds=6)

        recovered = scheduler.recover_expired("recover-job", "owner-b")

        self.assertEqual(len(recovered), 1)
        self.assertEqual(recovered[0].action_id, original.action_id)
        self.assertEqual(recovered[0].attempt_id, original.attempt_id)
        self.assertEqual(recovered[0].fence_epoch, original.fence_epoch + 1)
        self.assertEqual(recovered[0].owner_id, "owner-b")
        with self.assertRaises(FenceRejected):
            self.store.transition_outbox(
                original.action_id, "dispatched", "owner-a", original.fence_epoch,
            )

    def test_last_terminal_gate_atomically_closes_job(self) -> None:
        self.scheduler.register_job(
            "terminal-job", [
                {"id": "terminal-a", "type": "analysis"},
                {"id": "terminal-b", "type": "experiment"},
            ], [],
        )
        claims = self.scheduler.claim_ready("terminal-job", "owner-a")
        self.scheduler.complete_gate(claims[0], outcome="completed", evidence_hash="a" * 64)
        self.assertEqual(self.store.project_job_status("terminal-job")["job_state"], "running")
        self.scheduler.complete_gate(claims[1], outcome="completed", evidence_hash="b" * 64)
        self.assertEqual(self.store.project_job_status("terminal-job")["job_state"], "terminal")

    def tearDown(self) -> None:
        self.store.close()
        self.temporary.cleanup()

    def register(self, job_id: str = "job-1") -> None:
        self.scheduler.register_job(
            job_id,
            [
                {"id": "gate-a", "type": "experiment", "priority": 30},
                {"id": "gate-b", "type": "analysis", "priority": 20},
                {"id": "gate-c", "type": "analysis", "priority": 10},
            ],
            [],
        )

    def test_bounded_concurrency_claims_only_two_ready_gates(self) -> None:
        self.register()
        first = self.scheduler.claim_ready("job-1", "owner-1")
        second = self.scheduler.claim_ready("job-1", "owner-1")
        self.assertEqual([claim.work_item_id for claim in first], ["gate-a", "gate-b"])
        self.assertEqual(second, [])

    def test_claim_atomically_creates_attempt_action_and_outbox(self) -> None:
        self.register()
        claims = self.scheduler.claim_ready("job-1", "owner-1")
        for claim in claims:
            with self.subTest(gate=claim.work_item_id):
                self.assertEqual(
                    claim.attempt_id,
                    f"{claim.work_item_id}:attempt:{claim.attempt_number}",
                )
                self.assertEqual(
                    claim.action_id,
                    f"{claim.work_item_id}:action:{claim.attempt_number}",
                )
                action = self.store.action_context(claim.action_id)
                self.assertEqual(action["attempt_id"], claim.attempt_id)
                outbox = self.store.connection.execute(
                    "SELECT state FROM outbox WHERE action_id=?", (claim.action_id,)
                ).fetchone()
                self.assertEqual(outbox[0], "queued")

    def test_rate_limited_gate_does_not_starve_independent_gate(self) -> None:
        self.register()
        claims = self.scheduler.claim_ready("job-1", "owner-1")
        by_id = {claim.work_item_id: claim for claim in claims}
        decision = self.scheduler.record_failure(
            by_id["gate-a"], layer="provider", http_status=429,
            retry_after_seconds=60, evidence_hash="a" * 64,
        )
        self.scheduler.complete_gate(
            by_id["gate-b"], outcome="completed", evidence_hash="b" * 64
        )

        next_claims = self.scheduler.claim_ready("job-1", "owner-1")
        self.assertEqual(decision.disposition, "cooldown")
        self.assertEqual([claim.work_item_id for claim in next_claims], ["gate-c"])
        self.assertEqual(self.store.work_item("gate-a")["state"], "cooldown")

    def test_auth_and_ambiguous_freeze_only_affected_gates(self) -> None:
        self.register()
        claims = self.scheduler.claim_ready("job-1", "owner-1")
        by_id = {claim.work_item_id: claim for claim in claims}
        self.scheduler.record_failure(
            by_id["gate-a"], layer="auth", evidence_hash="a" * 64
        )
        self.scheduler.record_failure(
            by_id["gate-b"], layer="ambiguous-transport", evidence_hash="b" * 64
        )

        self.assertEqual(self.store.work_item("gate-a")["state"], "awaiting_user_action")
        self.assertEqual(self.store.work_item("gate-b")["state"], "reconciling")
        next_claims = self.scheduler.claim_ready("job-1", "owner-1")
        self.assertEqual([claim.work_item_id for claim in next_claims], ["gate-c"])

    def test_same_failure_signature_opens_fifteen_minute_circuit(self) -> None:
        self.scheduler.register_job(
            "job-1", [{"id": "gate-a", "type": "experiment", "priority": 1}], []
        )
        for attempt in range(5):
            claim = self.scheduler.claim_ready("job-1", "owner-1")[0]
            self.scheduler.record_failure(
                claim, layer="provider", http_status=500,
                retry_after_seconds=1, evidence_hash=f"{attempt:064x}",
            )
            if attempt < 4:
                self.clock.value += timedelta(seconds=2)
                self.scheduler.requeue_due("job-1")

        item = self.store.work_item("gate-a")
        self.assertEqual(item["circuit_state"], "open")
        self.assertEqual(item["failure_streak"], 5)
        self.assertEqual(item["next_eligible_at"], "2026-07-31T01:15:08Z")

    def test_retry_budget_leaves_capacity_for_normal_gate(self) -> None:
        self.register()
        first = self.scheduler.claim_ready("job-1", "owner-1")
        for claim in first:
            self.scheduler.record_failure(
                claim, layer="provider", http_status=500,
                retry_after_seconds=1, evidence_hash=claim.work_item_id.encode().hex().ljust(64, "0"),
            )
        self.clock.value += timedelta(seconds=2)
        self.scheduler.requeue_due("job-1")

        claims = self.scheduler.claim_ready("job-1", "owner-1")
        self.assertEqual(len([claim for claim in claims if claim.attempt_number > 1]), 1)
        self.assertIn("gate-c", [claim.work_item_id for claim in claims])

    def test_valid_negative_creates_one_durable_next_iteration(self) -> None:
        self.scheduler.register_job(
            "job-1", [{"id": "experiment-1", "type": "experiment", "priority": 1}], []
        )
        claim = self.scheduler.claim_ready("job-1", "owner-1")[0]
        successor = self.scheduler.complete_gate(
            claim, outcome="valid_negative", evidence_hash="c" * 64
        )
        repeated = self.scheduler.complete_gate(
            claim, outcome="valid_negative", evidence_hash="c" * 64
        )

        self.assertEqual(successor, "experiment-1:iteration:2")
        self.assertEqual(repeated, successor)
        self.assertEqual(self.store.work_item(successor)["state"], "pending")
        self.assertEqual(
            self.store.dependency(successor),
            {"predecessor_id": "experiment-1", "required_outcome": "valid_negative"},
        )

    def test_dependency_cycle_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.scheduler.register_job(
                "job-cycle",
                [
                    {"id": "a", "type": "analysis"},
                    {"id": "b", "type": "analysis"},
                ],
                [
                    {"predecessor_id": "a", "successor_id": "b"},
                    {"predecessor_id": "b", "successor_id": "a"},
                ],
            )

    def test_each_gate_has_independent_thread_and_handoff_has_one_successor(self) -> None:
        self.register()
        claims = self.scheduler.claim_ready("job-1", "owner-1")
        first, second = claims
        self.store.bind_canonical_thread(
            first.attempt_id, "app-server", "thread-a", "schema", first.owner_id,
            first.fence_epoch,
        )
        self.store.bind_canonical_thread(
            second.attempt_id, "app-server", "thread-b", "schema", second.owner_id,
            second.fence_epoch,
        )
        successor = self.scheduler.create_context_handoff(
            first, state_pack_hash="d" * 64, evidence_hash="e" * 64
        )
        repeated = self.scheduler.create_context_handoff(
            first, state_pack_hash="d" * 64, evidence_hash="e" * 64
        )

        self.assertNotEqual(
            self.store.thread_binding(first.attempt_id)["thread_id"],
            self.store.thread_binding(second.attempt_id)["thread_id"],
        )
        self.assertEqual(successor, repeated)
        self.assertEqual(successor, "gate-a:attempt:2")
        with self.assertRaises(IntegrityIncident):
            self.scheduler.create_context_handoff(
                first, state_pack_hash="f" * 64, evidence_hash="e" * 64
            )

    def test_phase3_workflow_names_are_additive_and_versioned(self) -> None:
        self.assertEqual(WORKFLOW_REGISTRY["run_action_v1"], {"version": 1})
        self.assertEqual(WORKFLOW_REGISTRY["run_codex_action_v1"], {"version": 1})
        for name in ("schedule_job_v1", "cooldown_gate_v1", "reconcile_gate_v1"):
            self.assertEqual(WORKFLOW_REGISTRY[name], {"version": 1})

    def test_status_requires_heartbeat_lease_and_outbox_for_continuation(self) -> None:
        self.register()
        claims = self.scheduler.claim_ready("job-1", "owner-1")
        self.store.record_supervisor_heartbeat(
            "supervisor-1", "owner-1", controller_pid=1234,
            witness_hash="f" * 64, ttl_seconds=60,
        )
        status = self.store.project_job_status("job-1", supervisor_id="supervisor-1")
        gates = {gate["work_item_id"]: gate for gate in status["gates"]}

        self.assertEqual(len(gates), 3)
        self.assertTrue(status["continuation_confirmed"])
        self.assertTrue(gates[claims[0].work_item_id]["continuation_confirmed"])
        self.assertFalse(status["release_allowed"])

        self.clock.value += timedelta(seconds=121)
        stale = self.store.project_job_status("job-1", supervisor_id="supervisor-1")
        self.assertFalse(stale["continuation_confirmed"])
        self.assertTrue(stale["supervisor_stale"])

    def test_cooldown_body_wakes_only_due_gate_and_rejects_stale_fence(self) -> None:
        self.register()
        claims = self.scheduler.claim_ready("job-1", "owner-1")
        by_id = {claim.work_item_id: claim for claim in claims}
        self.scheduler.record_failure(
            by_id["gate-a"], layer="provider", http_status=429,
            retry_after_seconds=1, evidence_hash="a" * 64,
        )
        self.scheduler.record_failure(
            by_id["gate-b"], layer="provider", http_status=429,
            retry_after_seconds=100, evidence_hash="b" * 64,
        )
        self.clock.value += timedelta(seconds=2)

        result = _cooldown_gate_body(
            "gate-a", str(self.store.path), "owner-1", by_id["gate-a"].fence_epoch,
            delay_seconds=0, sleep_fn=lambda _: None, now=self.clock.value,
        )
        self.assertEqual(result["terminal_status"], "ready")
        self.assertEqual(self.store.work_item("gate-a")["state"], "pending")
        self.assertEqual(self.store.work_item("gate-b")["state"], "cooldown")

        self.store.acquire_lease(
            "gate-a", "owner-2", allow_unexpired_takeover=True
        )
        stale = _cooldown_gate_body(
            "gate-a", str(self.store.path), "owner-1", by_id["gate-a"].fence_epoch,
            delay_seconds=0, sleep_fn=lambda _: None, now=self.clock.value,
        )
        self.assertEqual(stale["terminal_status"], "fenced")


if __name__ == "__main__":
    unittest.main()
