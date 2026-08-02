import json
import queue
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTROLLER_ROOT = ROOT / "plugins" / "deepscientist-lite-core" / "controller"
SCHEMA_ROOT = ROOT / "plugins" / "deepscientist-lite-core" / "schemas" / "codex" / "0.128.0"
sys.path.insert(0, str(CONTROLLER_ROOT))

from ds_lite_control.app_server import (
    AppServerAdapter,
    AppServerClosed,
    AppServerResponseTimeout,
    ProtocolSpool,
    SchemaRegistry,
    SchemaValidationError,
)


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


class Phase2AppServerTests(unittest.TestCase):
    def test_schema_registry_rejects_guessed_and_missing_fields(self):
        schemas = SchemaRegistry(SCHEMA_ROOT)
        with self.assertRaises(SchemaValidationError):
            schemas.validate("thread/read", {"threadId": "t", "guessed": True})
        with self.assertRaises(SchemaValidationError):
            schemas.validate("turn/start", {"threadId": "t"})
        schemas.validate("turn/start", {
            "threadId": "t", "input": [{"type": "text", "text": "OK"}],
        })
        schemas.validate("model/list", {"includeHidden": False})

    def test_model_catalog_and_explicit_turn_model_are_schema_bound(self):
        def on_write(message):
            if message["method"] == "model/list":
                process.emit({
                    "id": message["id"],
                    "result": {
                        "data": [{
                            "id": "model-current",
                            "model": "model-current",
                            "displayName": "Current",
                            "description": "available",
                            "hidden": False,
                            "isDefault": True,
                            "defaultReasoningEffort": "medium",
                            "supportedReasoningEfforts": [],
                        }],
                        "nextCursor": None,
                    },
                })
            elif message["method"] == "turn/start":
                process.emit({"id": message["id"], "result": {"turn": {"id": "turn-1"}}})

        process = FakeProcess(on_write)
        adapter = AppServerAdapter(process, SCHEMA_ROOT, response_timeout=0.5)
        catalog = adapter.list_models(include_hidden=False, request_id="models")
        self.assertEqual(catalog.response["result"]["data"][0]["model"], "model-current")
        adapter.start_turn(
            "thread-1", [{"type": "text", "text": "OK"}],
            request_id="turn", model="model-current",
        )
        turn_request = next(row for row in process.writes if row["method"] == "turn/start")
        self.assertEqual(turn_request["params"]["model"], "model-current")
        process.close()

    def test_failed_terminal_notification_is_not_completed(self):
        process = FakeProcess(lambda message: None)
        adapter = AppServerAdapter(process, SCHEMA_ROOT, response_timeout=0.1)
        process.emit({
            "method": "turn/completed",
            "params": {
                "threadId": "thread-1",
                "turn": {"id": "turn-1", "status": "failed"},
            },
        })
        observation = adapter.observe_turn("thread-1", "turn-1", timeout=0.2)
        self.assertEqual(observation.disposition, "failed")
        process.close()

    def test_notification_before_response_is_preserved_and_correlated(self):
        def on_write(message):
            if message["method"] == "turn/start":
                process.emit({
                    "method": "turn/completed",
                    "params": {"threadId": "thread-1", "turn": {"id": "turn-1", "status": "completed"}},
                })
                process.emit({"id": message["id"], "result": {"turn": {"id": "turn-1"}}})

        process = FakeProcess(on_write)
        adapter = AppServerAdapter(process, SCHEMA_ROOT, response_timeout=1)
        observation = adapter.start_turn(
            "thread-1", [{"type": "text", "text": "OK"}], request_id="request-1",
        )
        terminal = adapter.observe_turn("thread-1", "turn-1", timeout=1)
        self.assertEqual(observation.disposition, "acknowledged")
        self.assertEqual(observation.turn_id, "turn-1")
        self.assertEqual(terminal.disposition, "terminal")
        self.assertEqual(adapter.transport.unmatched_response_count, 0)

    def test_response_loss_keeps_notification_and_never_starts_fallback(self):
        def on_write(message):
            if message["method"] == "turn/start":
                process.emit({
                    "method": "turn/started",
                    "params": {"threadId": "thread-1", "turn": {"id": "turn-1", "status": "inProgress"}},
                })

        process = FakeProcess(on_write)
        adapter = AppServerAdapter(process, SCHEMA_ROOT, response_timeout=0.05)
        with self.assertRaises(AppServerResponseTimeout):
            adapter.start_turn(
                "thread-1", [{"type": "text", "text": "OK"}], request_id="request-1",
            )
        active = adapter.observe_turn("thread-1", "turn-1", timeout=0)
        self.assertEqual(active.disposition, "active")
        self.assertEqual([row["method"] for row in process.writes], ["turn/start"])

    def test_process_exit_wakes_all_waiters(self):
        process = FakeProcess(lambda message: None)
        adapter = AppServerAdapter(process, SCHEMA_ROOT, response_timeout=2)
        failures = []

        def request_read(thread_id):
            try:
                adapter.read_thread(thread_id)
            except Exception as exc:
                failures.append(exc)

        threads = [threading.Thread(target=request_read, args=(f"thread-{index}",)) for index in range(2)]
        for thread in threads:
            thread.start()
        deadline = time.monotonic() + 1
        while len(process.writes) < 2 and time.monotonic() < deadline:
            time.sleep(0.01)
        process.close()
        for thread in threads:
            thread.join(timeout=1)
        self.assertEqual(len(failures), 2)
        self.assertTrue(all(isinstance(exc, AppServerClosed) for exc in failures))
        self.assertEqual(adapter.transport.waiter_count, 0)

    def test_protocol_spool_is_append_only_and_hashes_payload(self):
        with tempfile.TemporaryDirectory(prefix="ds-lite-protocol-") as directory:
            spool = ProtocolSpool(Path(directory) / "protocol.jsonl")
            first = spool.append("outbound", {"id": 1, "method": "thread/read", "params": {"threadId": "t"}})
            second = spool.append("inbound", {"id": 1, "result": {"thread": {"id": "t"}}})
            rows = [json.loads(line) for line in spool.path.read_text(encoding="utf-8").splitlines()]
            self.assertEqual([row["sequence"] for row in rows], [1, 2])
            self.assertEqual(rows[0]["payload_sha256"], first["payload_sha256"])
            self.assertEqual(rows[1]["payload_sha256"], second["payload_sha256"])
            self.assertNotIn("payload", rows[0])


if __name__ == "__main__":
    unittest.main()
