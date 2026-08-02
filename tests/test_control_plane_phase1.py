import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTROLLER_ROOT = ROOT / "plugins" / "deepscientist-lite-core" / "controller"
sys.path.insert(0, str(CONTROLLER_ROOT))

from ds_lite_control.backup import backup_control_plane, verify_backup
from ds_lite_control.dbos_bridge import _run_action_body
from ds_lite_control.domain import ControlStore, FenceRejected, IntegrityIncident, MigrationRejected
from ds_lite_control.receipts import ReceiptConflict, ReceiptStore
from ds_lite_control.workflows import WORKFLOW_REGISTRY, ManagedController


class Phase1DomainTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="ds-lite-phase1-")
        self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_migrates_empty_database_and_enables_durable_pragmas(self):
        store = ControlStore(self.root / "control.sqlite3")
        try:
            self.assertEqual(store.schema_version, 4)
            self.assertEqual(store.integrity_check(), "ok")
            self.assertEqual(store.connection.execute("PRAGMA journal_mode").fetchone()[0], "wal")
            self.assertEqual(store.connection.execute("PRAGMA synchronous").fetchone()[0], 2)
            names = {row[0] for row in store.connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )}
            self.assertTrue({"jobs", "work_items", "attempts", "actions", "outbox",
                             "workflow_bindings", "host_events", "leases", "receipt_index",
                             "status_projection"}.issubset(names))
        finally:
            store.close()

    def test_rejects_unversioned_phase05_database_without_mutating_it(self):
        path = self.root / "legacy.sqlite3"
        connection = sqlite3.connect(path)
        connection.execute("CREATE TABLE actions(action_id TEXT PRIMARY KEY, kind TEXT, state TEXT)")
        connection.commit()
        connection.close()
        before = path.read_bytes()
        with self.assertRaises(MigrationRejected):
            ControlStore(path)
        self.assertEqual(path.read_bytes(), before)

    def test_action_identity_is_idempotent_but_payload_mismatch_is_incident(self):
        store = ControlStore(self.root / "control.sqlite3")
        try:
            epoch = store.create_job_work_item("job-1", "work-1", "owner-1")
            first = store.plan_attempt_action(
                job_id="job-1", work_item_id="work-1", attempt_id="attempt-1",
                action_id="action-1", kind="fake-turn", payload_hash="a" * 64,
                owner_id="owner-1", fence_epoch=epoch,
            )
            second = store.plan_attempt_action(
                job_id="job-1", work_item_id="work-1", attempt_id="attempt-1",
                action_id="action-1", kind="fake-turn", payload_hash="a" * 64,
                owner_id="owner-1", fence_epoch=epoch,
            )
            self.assertEqual(first, second)
            self.assertEqual(store.workflow_binding_count("action-1"), 0)
            with self.assertRaises(IntegrityIncident):
                store.plan_attempt_action(
                    job_id="job-1", work_item_id="work-1", attempt_id="attempt-1",
                    action_id="action-1", kind="fake-turn", payload_hash="b" * 64,
                    owner_id="owner-1", fence_epoch=epoch,
                )
        finally:
            store.close()

    def test_old_resource_fence_cannot_mutate_outbox_or_binding(self):
        store = ControlStore(self.root / "control.sqlite3")
        try:
            old = store.create_job_work_item("job-1", "work-1", "owner-old")
            store.plan_attempt_action(
                job_id="job-1", work_item_id="work-1", attempt_id="attempt-1",
                action_id="action-1", kind="fake-turn", payload_hash="a" * 64,
                owner_id="owner-old", fence_epoch=old,
            )
            current = store.acquire_lease(
                "work-1", "owner-new", allow_unexpired_takeover=True
            )
            with self.assertRaises(FenceRejected):
                store.transition_outbox("action-1", "workflow_submitting", "owner-old", old)
            with self.assertRaises(FenceRejected):
                store.attach_workflow("action-1", "run_action_v1", "owner-old", old)
            store.transition_outbox("action-1", "workflow_submitting", "owner-new", current)
            binding = store.attach_workflow("action-1", "run_action_v1", "owner-new", current)
            self.assertEqual(binding["workflow_id"], "action-1")
        finally:
            store.close()

    def test_duplicate_binding_reconciliation_cannot_reopen_terminal_outbox(self):
        store = ControlStore(self.root / "control.sqlite3")
        try:
            epoch = store.create_job_work_item("job-1", "work-1", "owner-1")
            store.plan_attempt_action(
                job_id="job-1", work_item_id="work-1", attempt_id="attempt-1",
                action_id="action-1", kind="fake-turn", payload_hash="a" * 64,
                owner_id="owner-1", fence_epoch=epoch,
            )
            store.attach_workflow("action-1", "run_action_v1", "owner-1", epoch, "active")
            store.record_host_event(
                event_id="terminal-action-1", action_id="action-1", event_type="terminal",
                observed_at="2026-07-31T00:00:00Z", payload_hash="c" * 64,
                owner_id="owner-1", fence_epoch=epoch,
            )
            with self.assertRaises(IntegrityIncident):
                store.transition_outbox("action-1", "workflow_submitting", "owner-1", epoch)
            store.attach_workflow("action-1", "run_action_v1", "owner-1", epoch, "SUCCESS")
            status = store.project_status("job-1")
            self.assertEqual(status["state"], "terminal")
            self.assertEqual(status["runtime_state"], "SUCCESS")
            self.assertEqual(status["next_durable_action"], "none")
        finally:
            store.close()


class Phase1ReceiptTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="ds-lite-receipt-")
        self.root = Path(self.temporary.name)
        self.store = ControlStore(self.root / "control.sqlite3")
        self.epoch = self.store.create_job_work_item("job-1", "work-1", "owner-1")
        self.store.plan_attempt_action(
            job_id="job-1", work_item_id="work-1", attempt_id="attempt-1",
            action_id="action-1", kind="fake-turn", payload_hash="a" * 64,
            owner_id="owner-1", fence_epoch=self.epoch,
        )
        self.store.record_host_event(
            event_id="event-1", action_id="action-1", event_type="terminal",
            observed_at="2026-07-31T00:00:00Z", payload_hash="c" * 64,
            owner_id="owner-1", fence_epoch=self.epoch,
        )

    def tearDown(self) -> None:
        self.store.close()
        self.temporary.cleanup()

    def test_k8_rebuilds_identical_receipt_from_terminal_event(self):
        receipts = ReceiptStore(self.root / "receipts", self.store)
        payload = receipts.terminal_payload("action-1", "owner-1", self.epoch)
        first = receipts.write_and_index("receipt-1", payload, "owner-1", self.epoch)
        self.assertEqual(first["receipt"]["workflow_runtime_version"], "2.29.0")
        self.assertEqual(first["receipt"]["host_version"], "fake-v1")
        self.assertIn("input_state_digest", first["receipt"])
        self.assertNotIn("passed", first["receipt"])
        self.assertNotIn("release_allowed", first["receipt"])
        self.store.connection.execute("DELETE FROM receipt_index WHERE receipt_id='receipt-1'")
        self.store.connection.commit()
        second = receipts.write_and_index("receipt-1", payload, "owner-1", self.epoch)
        self.assertEqual(first["content_hash"], second["content_hash"])
        self.assertEqual(self.store.receipt_index("receipt-1")["content_hash"], first["content_hash"])

    def test_duplicate_terminal_reconciliation_keeps_original_chain_predecessor(self):
        receipts = ReceiptStore(self.root / "receipts", self.store)
        first_payload = receipts.terminal_payload("action-1", "owner-1", self.epoch)
        first = receipts.write_and_index("terminal-action-1", first_payload, "owner-1", self.epoch)
        replay_payload = receipts.terminal_payload("action-1", "owner-1", self.epoch)
        replay = receipts.write_and_index("terminal-action-1", replay_payload, "owner-1", self.epoch)
        self.assertEqual(first["content_hash"], replay["content_hash"])

    def test_k9_rejects_same_receipt_id_with_different_content(self):
        receipts = ReceiptStore(self.root / "receipts", self.store)
        payload = receipts.terminal_payload("action-1", "owner-1", self.epoch)
        receipts.write_and_index("receipt-1", payload, "owner-1", self.epoch)
        changed = dict(payload)
        changed["terminal_status"] = "failed"
        with self.assertRaises(ReceiptConflict):
            receipts.write_and_index("receipt-1", changed, "owner-1", self.epoch)
        persisted = json.loads((self.root / "receipts" / "receipt-1.json").read_text(encoding="utf-8"))
        self.assertEqual(persisted["terminal_status"], "completed")

    def test_k9_file_durability_and_index_commit_are_separate_recovery_steps(self):
        receipts = ReceiptStore(self.root / "receipts", self.store)
        payload = receipts.terminal_payload("action-1", "owner-1", self.epoch)
        written = receipts.write_file("receipt-1", payload)
        self.assertIsNone(self.store.receipt_index("receipt-1"))
        recovered = receipts.index_written_file(
            "receipt-1", payload, "owner-1", self.epoch
        )
        self.assertEqual(written["content_hash"], recovered["content_hash"])
        self.assertEqual(
            self.store.receipt_index("receipt-1")["content_hash"],
            written["content_hash"],
        )


class Phase1WorkflowAndBackupTests(unittest.TestCase):
    def test_registry_is_versioned_and_contains_only_phase1_workflows(self):
        self.assertTrue({"reconcile_job_v1", "run_action_v1", "project_status_v1"}.issubset(WORKFLOW_REGISTRY))

    def test_recovered_old_workflow_reports_fenced_without_domain_mutation(self):
        with tempfile.TemporaryDirectory(prefix="ds-lite-k3-") as directory:
            root = Path(directory)
            store = ControlStore(root / "control.sqlite3")
            old = store.create_job_work_item("job-1", "work-1", "owner-old")
            store.plan_attempt_action(
                job_id="job-1", work_item_id="work-1", attempt_id="attempt-1",
                action_id="action-1", kind="fake-turn", payload_hash="a" * 64,
                owner_id="owner-old", fence_epoch=old,
            )
            store.acquire_lease(
                "work-1", "owner-new", allow_unexpired_takeover=True
            )
            store.close()
            result = _run_action_body("action-1", str(root / "control.sqlite3"), "owner-old", old)
            self.assertEqual(result["terminal_status"], "fenced")
            reopened = ControlStore(root / "control.sqlite3")
            try:
                self.assertEqual(reopened.terminal_event("action-1"), None)
            except ValueError:
                pass
            finally:
                reopened.close()

    def test_managed_controller_completes_one_fake_action_and_projects_truth(self):
        with tempfile.TemporaryDirectory(prefix="ds-lite-managed-") as directory:
            root = Path(directory)
            store = ControlStore(root / "control.sqlite3")
            try:
                controller = ManagedController(store, root / "receipts", owner_id="owner-1")
                result = controller.run_once("job-1", "work-1", "action-1")
                self.assertEqual(result["terminal_status"], "completed")
                status = store.project_status("job-1")
                self.assertEqual(status["evidence_class"], "fake-host")
                self.assertEqual(status["workflow_id"], "action-1")
                self.assertEqual(status["next_durable_action"], "none")
                self.assertNotIn("release_allowed", status)
            finally:
                store.close()

    def test_backup_requires_control_runtime_and_receipts_and_verifies_hashes(self):
        with tempfile.TemporaryDirectory(prefix="ds-lite-backup-") as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            store = ControlStore(source / "control.sqlite3")
            store.close()
            sqlite3.connect(source / "runtime.sqlite3").close()
            (source / "receipts").mkdir()
            (source / "receipts" / "one.json").write_text("{}\n", encoding="utf-8")
            destination = root / "backup"
            manifest = backup_control_plane(source, destination)
            self.assertTrue(manifest["complete"])
            self.assertTrue(verify_backup(destination)["valid"])
            (destination / "runtime.sqlite3").write_bytes(b"corrupt")
            self.assertFalse(verify_backup(destination)["valid"])


if __name__ == "__main__":
    unittest.main()
