import json
import queue
import sys
import tempfile
import threading
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTROLLER_ROOT = ROOT / "plugins" / "deepscientist-lite-core" / "controller"
SCHEMA_ROOT = ROOT / "plugins" / "deepscientist-lite-core" / "schemas" / "codex" / "0.128.0"
sys.path.insert(0, str(CONTROLLER_ROOT))

from ds_lite_control.app_server import AppServerClosed
from ds_lite_control.broker import (
    BrokerAppServerAdapter,
    BrokerService,
    DurableWireJournal,
)
from ds_lite_control.codex_actions import CodexActionRunner
from ds_lite_control.store import ControlStore


class _Input:
    def __init__(self, process):
        self.process = process

    def write(self, value):
        message = json.loads(value)
        self.process.writes.append(message)
        self.process.on_write(message)

    def flush(self):
        return None


class _Output:
    def __init__(self, process):
        self.process = process

    def readline(self):
        return self.process.lines.get(timeout=5)


class FakeProcess:
    def __init__(self, on_write):
        self.lines = queue.Queue()
        self.writes = []
        self.on_write = on_write
        self.stdin = _Input(self)
        self.stdout = _Output(self)

    def emit(self, message):
        self.lines.put(json.dumps(message) + "\n")

    def close(self):
        self.lines.put("")


class Phase2BrokerTests(unittest.TestCase):
    def test_journal_is_durable_monotonic_and_hash_chained(self):
        with tempfile.TemporaryDirectory(prefix="ds-lite-broker-") as directory:
            path = Path(directory) / "wire.jsonl"
            journal = DurableWireJournal(path)
            journal.register_request(7, "action-1:turn-start", "connection-a")
            journal.append("outbound", {"id": 7, "method": "turn/start", "params": {"threadId": "t"}})
            journal.append("inbound", {"id": 7, "result": {"turn": {"id": "turn-1"}}})
            journal.mark_delivery(7, "connection-a", delivered=False)

            reopened = DurableWireJournal(path)
            rows = reopened.snapshot()
            self.assertEqual([row["sequence"] for row in rows], [1, 2, 3])
            self.assertTrue(reopened.verify()["valid"])
            self.assertEqual(reopened.response_for("action-1:turn-start")["result"]["turn"]["id"], "turn-1")
            self.assertFalse(rows[-1]["client_delivered"])

    def test_token_rejection_does_not_reach_host(self):
        process = FakeProcess(lambda message: None)
        with tempfile.TemporaryDirectory(prefix="ds-lite-broker-") as directory:
            service = BrokerService(process, SCHEMA_ROOT, Path(directory) / "wire.jsonl", token="right")
            service.start()
            try:
                adapter = BrokerAppServerAdapter(service.endpoint, "wrong", SCHEMA_ROOT, response_timeout=0.2)
                with self.assertRaises(PermissionError):
                    adapter.read_thread("thread-1")
                self.assertEqual(process.writes, [])
            finally:
                service.close()
                process.close()

    def test_dropped_real_response_is_replayed_without_second_host_request(self):
        def on_write(message):
            if message["method"] == "turn/start":
                process.emit({
                    "method": "turn/started",
                    "params": {"threadId": "thread-1", "turn": {"id": "turn-1", "status": "inProgress"}},
                })
                process.emit({"id": message["id"], "result": {"turn": {"id": "turn-1"}}})

        process = FakeProcess(on_write)
        with tempfile.TemporaryDirectory(prefix="ds-lite-broker-") as directory:
            service = BrokerService(process, SCHEMA_ROOT, Path(directory) / "wire.jsonl", token="secret")
            service.start()
            try:
                first = BrokerAppServerAdapter(service.endpoint, "secret", SCHEMA_ROOT, response_timeout=0.5)
                first.transport.drop_next_response("turn/start")
                with self.assertRaises(AppServerClosed):
                    first.start_turn(
                        "thread-1", [{"type": "text", "text": "OK"}],
                        request_id="action-1:turn-start", wire_request_id=41,
                    )

                second = BrokerAppServerAdapter(service.endpoint, "secret", SCHEMA_ROOT, response_timeout=0.5)
                replayed = second.start_turn(
                    "thread-1", [{"type": "text", "text": "OK"}],
                    request_id="action-1:turn-start", wire_request_id=41,
                )
                self.assertEqual(replayed.turn_id, "turn-1")
                self.assertEqual([row["method"] for row in process.writes], ["turn/start"])
                active = second.observe_turn("thread-1", "turn-1", timeout=0)
                self.assertEqual(active.disposition, "active")
            finally:
                service.close()
                process.close()

    def test_written_request_without_host_response_stays_ambiguous(self):
        process = FakeProcess(lambda message: None)
        with tempfile.TemporaryDirectory(prefix="ds-lite-broker-") as directory:
            service = BrokerService(
                process, SCHEMA_ROOT, Path(directory) / "wire.jsonl",
                token="secret", host_response_timeout=0.05,
            )
            service.start()
            try:
                first = BrokerAppServerAdapter(service.endpoint, "secret", SCHEMA_ROOT, response_timeout=0.2)
                with self.assertRaises(Exception):
                    first.start_turn(
                        "thread-1", [{"type": "text", "text": "OK"}],
                        request_id="action-1:turn-start", wire_request_id=9,
                    )
                second = BrokerAppServerAdapter(service.endpoint, "secret", SCHEMA_ROOT, response_timeout=0.2)
                with self.assertRaises(Exception):
                    second.start_turn(
                        "thread-1", [{"type": "text", "text": "OK"}],
                        request_id="action-1:turn-start", wire_request_id=9,
                    )
                self.assertEqual(len(process.writes), 1)
            finally:
                service.close()
                process.close()

    def test_new_controller_reconciles_dropped_response_by_logical_request(self):
        def on_write(message):
            if message["method"] == "turn/start":
                process.emit({"id": message["id"], "result": {"turn": {"id": "turn-3"}}})
                threading.Timer(0.05, lambda: process.emit({
                    "method": "turn/completed",
                    "params": {"threadId": "thread-1", "turn": {"id": "turn-3", "status": "completed"}},
                })).start()

        process = FakeProcess(on_write)
        with tempfile.TemporaryDirectory(prefix="ds-lite-broker-") as directory:
            root = Path(directory)
            store = ControlStore(root / "control.sqlite3")
            epoch = store.create_job_work_item("job-1", "work-1", "owner-1")
            store.plan_attempt_action(
                job_id="job-1", work_item_id="work-1", attempt_id="attempt-1",
                action_id="action-1", kind="codex-turn", payload_hash="a" * 64,
                owner_id="owner-1", fence_epoch=epoch,
            )
            store.bind_canonical_thread(
                "attempt-1", "codex-app-server", "thread-1", "schema", "owner-1", epoch,
            )
            service = BrokerService(process, SCHEMA_ROOT, root / "wire.jsonl", token="secret")
            service.start()
            try:
                for historical_turn in ("turn-1", "turn-2"):
                    process.emit({
                        "method": "turn/completed",
                        "params": {"threadId": "thread-1", "turn": {"id": historical_turn, "status": "completed"}},
                    })
                worker_a = BrokerAppServerAdapter(
                    service.endpoint, "secret", SCHEMA_ROOT, response_timeout=0.5, connection_id="worker-a",
                )
                worker_a.transport.drop_next_response("turn/start")
                first = CodexActionRunner(store, worker_a).dispatch_turn(
                    "action-1", "attempt-1", [{"type": "text", "text": "OK"}], "owner-1", epoch,
                )
                self.assertEqual(first.disposition, "ambiguous")

                worker_b = BrokerAppServerAdapter(
                    service.endpoint, "secret", SCHEMA_ROOT, response_timeout=0.5, connection_id="worker-b",
                )
                recovered = CodexActionRunner(store, worker_b).reconcile_turn(
                    "action-1", "owner-1", epoch, observe_timeout=1.0,
                )
                self.assertEqual(recovered.turn_id, "turn-3")
                self.assertEqual(recovered.disposition, "terminal")
                self.assertEqual(store.rpc_request("action-1:turn-start")["state"], "terminal")
                self.assertEqual([row["method"] for row in process.writes], ["turn/start"])
            finally:
                service.close()
                process.close()
                store.close()

    def test_pending_archive_reconciles_by_exact_lists_without_redispatch(self):
        def on_write(message):
            if message["method"] == "thread/archive":
                process.emit({"id": message["id"], "result": {}})
            elif message["method"] == "thread/list":
                rows = [{"id": "thread-1"}] if message["params"].get("archived") is True else []
                process.emit({"id": message["id"], "result": {"data": rows}})

        process = FakeProcess(on_write)
        with tempfile.TemporaryDirectory(prefix="ds-lite-broker-") as directory:
            root = Path(directory)
            store = ControlStore(root / "control.sqlite3")
            epoch = store.create_job_work_item("job-1", "work-1", "worker-a")
            store.plan_attempt_action(
                job_id="job-1", work_item_id="work-1", attempt_id="attempt-1",
                action_id="action-1", kind="codex-turn", payload_hash="a" * 64,
                owner_id="worker-a", fence_epoch=epoch,
            )
            store.bind_canonical_thread(
                "attempt-1", "codex-app-server", "thread-1", "schema", "worker-a", epoch,
            )
            service = BrokerService(process, SCHEMA_ROOT, root / "wire.jsonl", token="secret")
            service.start()
            try:
                worker_a = BrokerAppServerAdapter(
                    service.endpoint, "secret", SCHEMA_ROOT, response_timeout=0.5, connection_id="worker-a",
                )
                worker_a.transport.drop_next_response("thread/archive")
                first = CodexActionRunner(store, worker_a).dispatch_archive(
                    "action-1", "attempt-1", "worker-a", epoch,
                )
                self.assertEqual(first.disposition, "ambiguous")
                self.assertEqual(store.thread_binding("attempt-1")["pending_archive"], 1)

                next_epoch = store.acquire_lease(
                    "work-1", "worker-b", allow_unexpired_takeover=True
                )
                worker_b = BrokerAppServerAdapter(
                    service.endpoint, "secret", SCHEMA_ROOT, response_timeout=0.5, connection_id="worker-b",
                )
                recovered = CodexActionRunner(store, worker_b).reconcile_archive(
                    "action-1", "attempt-1", "worker-b", next_epoch,
                )
                self.assertEqual(recovered.disposition, "terminal")
                binding = store.thread_binding("attempt-1")
                self.assertEqual(binding["pending_archive"], 0)
                self.assertEqual(binding["lifecycle_state"], "archived")
                self.assertEqual([row["method"] for row in process.writes].count("thread/archive"), 1)
            finally:
                service.close()
                process.close()
                store.close()


if __name__ == "__main__":
    unittest.main()
