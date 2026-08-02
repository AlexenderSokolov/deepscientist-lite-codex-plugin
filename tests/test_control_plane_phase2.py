import hashlib
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTROLLER_ROOT = ROOT / "plugins" / "deepscientist-lite-core" / "controller"
sys.path.insert(0, str(CONTROLLER_ROOT))

from ds_lite_control.domain import ControlStore, FenceRejected, IntegrityIncident
from ds_lite_control.backup import backup_control_plane, restore_control_plane, verify_backup
from ds_lite_control.migrations import SCHEMA_V1


class Phase2DomainTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="ds-lite-phase2-")
        self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _planned_store(self) -> tuple[ControlStore, int]:
        store = ControlStore(self.root / "control.sqlite3")
        epoch = store.create_job_work_item("job-1", "work-1", "owner-1")
        store.plan_attempt_action(
            job_id="job-1", work_item_id="work-1", attempt_id="attempt-1",
            action_id="action-1", kind="codex-turn", payload_hash="a" * 64,
            owner_id="owner-1", fence_epoch=epoch,
        )
        return store, epoch

    def test_v1_database_migrates_explicitly_to_current_schema(self):
        path = self.root / "control.sqlite3"
        connection = sqlite3.connect(path)
        connection.executescript(SCHEMA_V1)
        connection.commit()
        connection.close()

        migrated = ControlStore(path)
        try:
            self.assertEqual(migrated.schema_version, 4)
            tables = {row[0] for row in migrated.connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )}
            self.assertTrue({"rpc_requests", "protocol_journal"}.issubset(tables))
            columns = {row[1] for row in migrated.connection.execute("PRAGMA table_info(thread_bindings)")}
            self.assertTrue({"lifecycle_state", "pending_archive", "owner_id", "fence_epoch"}.issubset(columns))
        finally:
            migrated.close()

    def test_canonical_thread_binding_is_fenced_and_immutable(self):
        store, epoch = self._planned_store()
        try:
            first = store.bind_canonical_thread(
                "attempt-1", "codex-app-server", "thread-1", "schema-digest",
                "owner-1", epoch,
            )
            second = store.bind_canonical_thread(
                "attempt-1", "codex-app-server", "thread-1", "schema-digest",
                "owner-1", epoch,
            )
            self.assertEqual(first, second)
            with self.assertRaises(IntegrityIncident):
                store.bind_canonical_thread(
                    "attempt-1", "codex-app-server", "thread-2", "schema-digest",
                    "owner-1", epoch,
                )
            store.acquire_lease(
                "work-1", "owner-2", allow_unexpired_takeover=True
            )
            with self.assertRaises(FenceRejected):
                store.set_thread_archive_pending("attempt-1", True, "owner-1", epoch)
        finally:
            store.close()

    def test_rpc_request_state_is_fenced_idempotent_and_monotonic(self):
        store, epoch = self._planned_store()
        try:
            planned = store.plan_rpc_request(
                request_id="request-1", action_id="action-1", method="turn/start",
                params_hash="b" * 64, pre_dispatch_turn_id="turn-0",
                owner_id="owner-1", fence_epoch=epoch,
            )
            self.assertEqual(planned["state"], "planned")
            store.transition_rpc_request(
                "request-1", "written", "owner-1", epoch, wire_request_id=7,
            )
            store.transition_rpc_request(
                "request-1", "acknowledged", "owner-1", epoch,
                thread_id="thread-1", turn_id="turn-1", response_hash="c" * 64,
            )
            with self.assertRaises(IntegrityIncident):
                store.transition_rpc_request("request-1", "written", "owner-1", epoch)
            with self.assertRaises(IntegrityIncident):
                store.plan_rpc_request(
                    request_id="request-1", action_id="action-1", method="turn/start",
                    params_hash="d" * 64, pre_dispatch_turn_id="turn-0",
                    owner_id="owner-1", fence_epoch=epoch,
                )
        finally:
            store.close()

    def test_protocol_journal_is_append_only_and_rejects_identity_conflict(self):
        store, epoch = self._planned_store()
        try:
            store.plan_rpc_request(
                request_id="request-1", action_id="action-1", method="turn/start",
                params_hash="b" * 64, pre_dispatch_turn_id=None,
                owner_id="owner-1", fence_epoch=epoch,
            )
            payload_hash = hashlib.sha256(b"notification").hexdigest()
            first = store.append_protocol_event(
                journal_id="event-1", request_id="request-1", direction="inbound",
                message_kind="notification", method="turn/started", wire_id=None,
                thread_id="thread-1", turn_id="turn-1", payload_hash=payload_hash,
                observed_at="2026-07-31T00:00:00Z", owner_id="owner-1", fence_epoch=epoch,
            )
            second = store.append_protocol_event(
                journal_id="event-1", request_id="request-1", direction="inbound",
                message_kind="notification", method="turn/started", wire_id=None,
                thread_id="thread-1", turn_id="turn-1", payload_hash=payload_hash,
                observed_at="2026-07-31T00:00:00Z", owner_id="owner-1", fence_epoch=epoch,
            )
            self.assertEqual(first, second)
            with self.assertRaises(IntegrityIncident):
                store.append_protocol_event(
                    journal_id="event-1", request_id="request-1", direction="inbound",
                    message_kind="notification", method="turn/completed", wire_id=None,
                    thread_id="thread-1", turn_id="turn-1", payload_hash=payload_hash,
                    observed_at="2026-07-31T00:00:00Z", owner_id="owner-1", fence_epoch=epoch,
                )
        finally:
            store.close()

    def test_phase2_backup_round_trip_includes_protocol_spool(self):
        source = self.root / "source"
        source.mkdir()
        store = ControlStore(source / "control.sqlite3")
        store.close()
        sqlite3.connect(source / "runtime.sqlite3").close()
        (source / "receipts").mkdir()
        (source / "protocol-journal.jsonl").write_text("{\"sequence\":1}\n", encoding="utf-8")
        backup = self.root / "backup"
        manifest = backup_control_plane(source, backup, require_protocol=True)
        self.assertIn("protocol-journal.jsonl", manifest["files"])
        restored = restore_control_plane(backup, self.root / "restored")
        self.assertTrue(restored["valid"])
        self.assertEqual(
            (self.root / "restored" / "protocol-journal.jsonl").read_text(encoding="utf-8"),
            "{\"sequence\":1}\n",
        )
        (backup / "protocol-journal.jsonl").write_text("tampered\n", encoding="utf-8")
        self.assertFalse(verify_backup(backup)["valid"])

    def test_broker_backup_requires_journal_and_redacted_metadata(self):
        source = self.root / "broker-source"
        source.mkdir()
        store = ControlStore(source / "control.sqlite3")
        store.close()
        sqlite3.connect(source / "runtime.sqlite3").close()
        (source / "receipts").mkdir()
        (source / "protocol-journal.jsonl").write_text(
            '{"sequence":1,"event_hash":"a"}\n', encoding="utf-8",
        )
        (source / "broker-metadata.json").write_text(
            '{"broker_id":"broker-1","app_server_pid":123}\n', encoding="utf-8",
        )
        manifest = backup_control_plane(source, self.root / "broker-backup", require_broker=True)
        self.assertEqual(manifest["schema_version"], "ds-lite.control-backup.v3")
        self.assertEqual(manifest["broker"]["last_sequence"], 1)
        self.assertNotIn("token", json.dumps(manifest))
        restored = restore_control_plane(self.root / "broker-backup", self.root / "broker-restored")
        self.assertTrue(restored["valid"])
        self.assertTrue((self.root / "broker-restored" / "broker-metadata.json").is_file())

    def test_status_projection_exposes_canonical_thread_and_pending_rpc(self):
        store, epoch = self._planned_store()
        try:
            store.bind_canonical_thread(
                "attempt-1", "codex-app-server", "thread-1", "schema", "owner-1", epoch,
            )
            store.plan_rpc_request(
                request_id="request-1", action_id="action-1", method="turn/start",
                params_hash="b" * 64, pre_dispatch_turn_id=None,
                owner_id="owner-1", fence_epoch=epoch,
            )
            status = store.project_status("job-1")
            self.assertEqual(status["canonical_thread_id"], "thread-1")
            self.assertEqual(status["rpc_state"], "planned")
            self.assertEqual(status["next_durable_action"], "dispatch:request-1")
        finally:
            store.close()


if __name__ == "__main__":
    unittest.main()
