"""Schema-bound, controller-owned Codex app-server adapter for Phase 2."""

from __future__ import annotations

import hashlib
import json
import queue
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol


class _Process(Protocol):
    stdin: Any
    stdout: Any


class AppServerProtocolError(RuntimeError):
    pass


class SchemaValidationError(AppServerProtocolError):
    pass


class AppServerClosed(AppServerProtocolError):
    pass


class AppServerResponseTimeout(AppServerProtocolError):
    pass


class SchemaRegistry:
    _methods = {
        "initialize": "v1/InitializeParams.json",
        "thread/start": "v2/ThreadStartParams.json",
        "thread/resume": "v2/ThreadResumeParams.json",
        "thread/list": "v2/ThreadListParams.json",
        "thread/read": "v2/ThreadReadParams.json",
        "thread/archive": "v2/ThreadArchiveParams.json",
        "thread/unarchive": "v2/ThreadUnarchiveParams.json",
        "model/list": "v2/ModelListParams.json",
        "turn/start": "v2/TurnStartParams.json",
    }

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.contract: dict[str, dict[str, list[str]]] = {}
        for method, relative in self._methods.items():
            payload = json.loads((self.root / relative).read_text(encoding="utf-8"))
            properties = payload.get("properties", {})
            self.contract[method] = {
                "required": [str(value) for value in payload.get("required", [])],
                "properties": sorted(str(value) for value in properties),
            }

    def validate(self, method: str, params: dict[str, Any]) -> None:
        specification = self.contract.get(method)
        if specification is None:
            raise SchemaValidationError(f"method-not-pinned:{method}")
        missing = sorted(set(specification["required"]) - set(params))
        unknown = sorted(set(params) - set(specification["properties"]))
        if missing:
            raise SchemaValidationError(f"required-field-missing:{','.join(missing)}")
        if unknown:
            raise SchemaValidationError(f"unrecognized-field:{','.join(unknown)}")


class ProtocolSpool:
    """Append-only protocol metadata spool; payload bodies are represented by hashes."""

    def __init__(self, path: Path) -> None:
        self.path = path.resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._sequence = self._load_sequence()

    def _load_sequence(self) -> int:
        if not self.path.exists():
            return 0
        lines = self.path.read_text(encoding="utf-8").splitlines()
        if not lines:
            return 0
        return int(json.loads(lines[-1])["sequence"])

    def append(self, direction: str, payload: dict[str, Any]) -> dict[str, Any]:
        if direction not in {"inbound", "outbound"}:
            raise ValueError("invalid protocol direction")
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
        with self._lock:
            self._sequence += 1
            row = {
                "sequence": self._sequence,
                "direction": direction,
                "message_kind": "notification" if "method" in payload and "id" not in payload else "response-or-request",
                "method": payload.get("method"),
                "wire_id": payload.get("id"),
                "payload_sha256": hashlib.sha256(encoded).hexdigest(),
            }
            with self.path.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(json.dumps(row, ensure_ascii=True, sort_keys=True) + "\n")
                handle.flush()
                import os
                os.fsync(handle.fileno())
            return row


@dataclass(frozen=True)
class RpcObservation:
    method: str
    request_id: str
    wire_request_id: int
    response: dict[str, Any] | None
    thread_id: str | None
    turn_id: str | None
    disposition: str


class _ClosedMarker:
    pass


class JsonRpcTransport:
    """Concurrent request transport with process-exit broadcast and notification retention."""

    def __init__(self, process: _Process, schemas: SchemaRegistry, *,
                 response_timeout: float = 30.0, spool: ProtocolSpool | None = None) -> None:
        if response_timeout <= 0:
            raise ValueError("response_timeout must be positive")
        self.process = process
        self.schemas = schemas
        self.response_timeout = response_timeout
        self.spool = spool
        self.next_request_id = 1
        self.notifications: list[dict[str, Any]] = []
        self.malformed_message_count = 0
        self.unmatched_response_count = 0
        self._lines: queue.Queue[str] = queue.Queue()
        self._waiters: dict[int, queue.Queue[dict[str, Any] | _ClosedMarker]] = {}
        self._waiters_lock = threading.Lock()
        self._write_lock = threading.Lock()
        self._notification_condition = threading.Condition()
        self._closed = threading.Event()
        threading.Thread(target=self._read_stdout, name="ds-lite-app-server-reader", daemon=True).start()

    @property
    def waiter_count(self) -> int:
        with self._waiters_lock:
            return len(self._waiters)

    def _read_stdout(self) -> None:
        while not self._closed.is_set():
            try:
                line = self.process.stdout.readline()
            except queue.Empty:
                time.sleep(0.001)
                continue
            if line == "":
                self._closed.set()
                with self._waiters_lock:
                    waiters = list(self._waiters.values())
                for waiter in waiters:
                    waiter.put(_ClosedMarker())
                with self._notification_condition:
                    self._notification_condition.notify_all()
                return
            try:
                message = json.loads(line)
            except (TypeError, json.JSONDecodeError):
                self.malformed_message_count += 1
                continue
            if not isinstance(message, dict):
                self.malformed_message_count += 1
                continue
            if self.spool is not None:
                self.spool.append("inbound", message)
            if "method" in message and "id" not in message:
                with self._notification_condition:
                    self.notifications.append(message)
                    self._notification_condition.notify_all()
                continue
            request_id = message.get("id")
            with self._waiters_lock:
                waiter = self._waiters.get(request_id)
            if waiter is None:
                self.unmatched_response_count += 1
            else:
                waiter.put(message)

    def request(self, method: str, params: dict[str, Any], *, wire_request_id: int | None = None) -> dict[str, Any]:
        self.schemas.validate(method, params)
        with self._write_lock:
            request_id = wire_request_id if wire_request_id is not None else self.next_request_id
            self.next_request_id = max(self.next_request_id, request_id + 1)
            waiter: queue.Queue[dict[str, Any] | _ClosedMarker] = queue.Queue(maxsize=1)
            with self._waiters_lock:
                self._waiters[request_id] = waiter
            payload = {"id": request_id, "method": method, "params": params}
            try:
                if self.spool is not None:
                    self.spool.append("outbound", payload)
                self.process.stdin.write(json.dumps(payload, ensure_ascii=True) + "\n")
                self.process.stdin.flush()
            except Exception:
                with self._waiters_lock:
                    self._waiters.pop(request_id, None)
                raise
        deadline = time.monotonic() + self.response_timeout
        try:
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise AppServerResponseTimeout("app-server-response-timeout")
                try:
                    message = waiter.get(timeout=remaining)
                except queue.Empty as exc:
                    raise AppServerResponseTimeout("app-server-response-timeout") from exc
                if isinstance(message, _ClosedMarker):
                    raise AppServerClosed("app-server-closed")
                return message
        finally:
            with self._waiters_lock:
                self._waiters.pop(request_id, None)

    def notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        if method != "initialized":
            raise AppServerProtocolError(f"notification-not-pinned:{method}")
        payload: dict[str, Any] = {"method": method}
        if params:
            payload["params"] = params
        with self._write_lock:
            if self.spool is not None:
                self.spool.append("outbound", payload)
            self.process.stdin.write(json.dumps(payload, ensure_ascii=True) + "\n")
            self.process.stdin.flush()

    def wait_for_notification(self, predicate: Any, *, timeout: float) -> dict[str, Any] | None:
        deadline = time.monotonic() + timeout
        with self._notification_condition:
            while True:
                for notification in self.notifications:
                    if predicate(notification):
                        return notification
                remaining = deadline - time.monotonic()
                if remaining <= 0 or self._closed.is_set():
                    return None
                self._notification_condition.wait(timeout=remaining)


class AppServerAdapter:
    """Exact-identity app-server facade. It never creates a fallback thread."""

    def __init__(self, process: _Process, schema_root: Path, *, response_timeout: float = 30.0,
                 spool: ProtocolSpool | None = None) -> None:
        self.schemas = SchemaRegistry(schema_root)
        self.transport = JsonRpcTransport(process, self.schemas, response_timeout=response_timeout, spool=spool)

    @staticmethod
    def _thread_id(response: dict[str, Any]) -> str | None:
        result = response.get("result")
        thread = result.get("thread") if isinstance(result, dict) else None
        return thread.get("id") if isinstance(thread, dict) and isinstance(thread.get("id"), str) else None

    @staticmethod
    def _turn_id(response: dict[str, Any]) -> str | None:
        result = response.get("result")
        turn = result.get("turn") if isinstance(result, dict) else None
        return turn.get("id") if isinstance(turn, dict) and isinstance(turn.get("id"), str) else None

    @staticmethod
    def _turn_disposition(notification: dict[str, Any]) -> str:
        params = notification.get("params")
        turn = params.get("turn") if isinstance(params, dict) else None
        status = turn.get("status") if isinstance(turn, dict) else None
        if notification.get("method") == "turn/failed" or status in {
            "failed", "cancelled", "interrupted",
        }:
            return "failed"
        if notification.get("method") == "turn/completed" and status in {None, "completed"}:
            return "terminal"
        return "active"

    def _request(self, method: str, params: dict[str, Any], request_id: str) -> RpcObservation:
        wire_id = self.transport.next_request_id
        response = self.transport.request(method, params, wire_request_id=wire_id)
        return RpcObservation(method, request_id, wire_id, response,
                              self._thread_id(response), self._turn_id(response), "acknowledged")

    def initialize(self, *, request_id: str = "initialize") -> RpcObservation:
        observation = self._request(
            "initialize", {"clientInfo": {"name": "ds-lite-control-plane", "version": "0.8.1"}}, request_id,
        )
        self.transport.notify("initialized")
        return observation

    def start_thread(self, params: dict[str, Any], *, request_id: str) -> RpcObservation:
        return self._request("thread/start", params, request_id)

    def resume_thread(self, thread_id: str, params: dict[str, Any] | None = None, *, request_id: str) -> RpcObservation:
        payload = dict(params or {})
        payload["threadId"] = thread_id
        return self._request("thread/resume", payload, request_id)

    def list_threads(self, params: dict[str, Any] | None = None, *, request_id: str) -> RpcObservation:
        return self._request("thread/list", dict(params or {}), request_id)

    def read_thread(self, thread_id: str, *, include_turns: bool = True, request_id: str = "thread-read") -> RpcObservation:
        return self._request("thread/read", {"threadId": thread_id, "includeTurns": include_turns}, request_id)

    def archive_thread(self, thread_id: str, *, request_id: str) -> RpcObservation:
        return self._request("thread/archive", {"threadId": thread_id}, request_id)

    def unarchive_thread(self, thread_id: str, *, request_id: str) -> RpcObservation:
        return self._request("thread/unarchive", {"threadId": thread_id}, request_id)

    def list_models(self, *, include_hidden: bool = False,
                    request_id: str = "model-list") -> RpcObservation:
        return self._request("model/list", {"includeHidden": include_hidden}, request_id)

    def start_turn(self, thread_id: str, input_items: list[dict[str, Any]], *, request_id: str,
                   wire_request_id: int | None = None,
                   model: str | None = None) -> RpcObservation:
        params: dict[str, Any] = {"threadId": thread_id, "input": input_items}
        if model is not None:
            params["model"] = model
        if wire_request_id is None:
            return self._request("turn/start", params, request_id)
        response = self.transport.request(
            "turn/start", params,
            wire_request_id=wire_request_id,
        )
        return RpcObservation("turn/start", request_id, wire_request_id, response,
                              self._thread_id(response), self._turn_id(response), "acknowledged")

    def observed_turns(self, thread_id: str) -> list[RpcObservation]:
        observations: list[RpcObservation] = []
        for notification in self.transport.notifications:
            params = notification.get("params")
            turn = params.get("turn") if isinstance(params, dict) else None
            if not isinstance(params, dict) or params.get("threadId") != thread_id or not isinstance(turn, dict):
                continue
            turn_id = turn.get("id")
            if not isinstance(turn_id, str):
                continue
            disposition = self._turn_disposition(notification)
            observations.append(RpcObservation("turn/observe", "observe", 0, notification,
                                               thread_id, turn_id, disposition))
        return observations

    def observe_turn(self, thread_id: str, turn_id: str, *, timeout: float) -> RpcObservation:
        def matches(notification: dict[str, Any]) -> bool:
            params = notification.get("params")
            if not isinstance(params, dict) or params.get("threadId") != thread_id:
                return False
            turn = params.get("turn")
            return isinstance(turn, dict) and turn.get("id") == turn_id

        terminal_methods = {"turn/completed", "turn/failed"}
        for notification in reversed(self.transport.notifications):
            if matches(notification) and notification.get("method") in terminal_methods:
                return RpcObservation(
                    "turn/observe", "observe", 0, notification, thread_id, turn_id,
                    self._turn_disposition(notification),
                )
        terminal = self.transport.wait_for_notification(
            lambda notification: matches(notification) and notification.get("method") in terminal_methods,
            timeout=timeout,
        )
        if terminal is not None:
            return RpcObservation(
                "turn/observe", "observe", 0, terminal, thread_id, turn_id,
                self._turn_disposition(terminal),
            )
        for notification in reversed(self.transport.notifications):
            if matches(notification):
                return RpcObservation("turn/observe", "observe", 0, notification, thread_id, turn_id, "active")
        return RpcObservation("turn/observe", "observe", 0, None, thread_id, turn_id, "ambiguous")
