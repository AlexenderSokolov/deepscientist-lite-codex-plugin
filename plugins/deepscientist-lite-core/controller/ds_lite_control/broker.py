"""Reconnectable loopback broker for real app-server fault acceptance."""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import socket
import socketserver
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .app_server import (
    AppServerAdapter,
    AppServerClosed,
    AppServerProtocolError,
    AppServerResponseTimeout,
    JsonRpcTransport,
    SchemaRegistry,
)


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _identity(frame: dict[str, Any]) -> tuple[str | None, str | None]:
    params = frame.get("params")
    result = frame.get("result")
    thread_id = params.get("threadId") if isinstance(params, dict) else None
    turn = params.get("turn") if isinstance(params, dict) else None
    if isinstance(result, dict):
        result_thread = result.get("thread")
        result_turn = result.get("turn")
        if isinstance(result_thread, dict):
            thread_id = result_thread.get("id", thread_id)
        if isinstance(result_turn, dict):
            turn = result_turn
    turn_id = turn.get("id") if isinstance(turn, dict) else None
    return (
        thread_id if isinstance(thread_id, str) else None,
        turn_id if isinstance(turn_id, str) else None,
    )


class DurableWireJournal:
    """Append-only full wire journal kept inside the isolated broker runtime."""

    def __init__(self, path: Path) -> None:
        self.path = path.resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._request_context: dict[int, tuple[str, str]] = {}
        self._rows = self._load()
        for row in self._rows:
            wire_id = row.get("wire_id")
            request_id = row.get("request_id")
            connection_id = row.get("connection_id")
            if row.get("direction") == "outbound" and isinstance(wire_id, int) and request_id:
                self._request_context[wire_id] = (str(request_id), str(connection_id or "unknown"))

    def _load(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        rows: list[dict[str, Any]] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if line:
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise ValueError("broker journal row must be an object")
                rows.append(value)
        return rows

    def register_request(self, wire_id: int, request_id: str, connection_id: str) -> None:
        with self._lock:
            existing = self._request_context.get(wire_id)
            candidate = (request_id, connection_id)
            if existing is not None and existing[0] != request_id:
                raise AppServerProtocolError("wire-request-id-conflict")
            self._request_context[wire_id] = candidate

    def _write(self, row: dict[str, Any]) -> dict[str, Any]:
        previous_hash = self._rows[-1]["event_hash"] if self._rows else None
        material = dict(row)
        material["sequence"] = len(self._rows) + 1
        material["previous_hash"] = previous_hash
        material["event_hash"] = hashlib.sha256(_canonical(material)).hexdigest()
        with self.path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(material, ensure_ascii=True, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        self._rows.append(material)
        return dict(material)

    def append(self, direction: str, payload: dict[str, Any]) -> dict[str, Any]:
        if direction not in {"inbound", "outbound"}:
            raise ValueError("invalid broker journal direction")
        with self._lock:
            wire_id = payload.get("id")
            context = self._request_context.get(wire_id) if isinstance(wire_id, int) else None
            request_id, connection_id = context if context else (None, None)
            method = payload.get("method")
            if method is None and context:
                outbound = self.outbound_for(str(request_id))
                method = outbound.get("method") if outbound else None
            thread_id, turn_id = _identity(payload)
            encoded = _canonical(payload)
            return self._write({
                "direction": direction,
                "connection_id": connection_id,
                "request_id": request_id,
                "wire_id": wire_id,
                "method": method,
                "thread_id": thread_id,
                "turn_id": turn_id,
                "payload_hash": hashlib.sha256(encoded).hexdigest(),
                "frame_hash": hashlib.sha256(encoded).hexdigest(),
                "host_observed": direction == "inbound",
                "client_delivered": None,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "frame": payload,
            })

    def mark_delivery(self, wire_id: int, connection_id: str, *, delivered: bool) -> dict[str, Any]:
        with self._lock:
            context = self._request_context.get(wire_id)
            request_id = context[0] if context else None
            return self._write({
                "direction": "broker",
                "connection_id": connection_id,
                "request_id": request_id,
                "wire_id": wire_id,
                "method": "response/delivery",
                "thread_id": None,
                "turn_id": None,
                "payload_hash": hashlib.sha256(b"{}").hexdigest(),
                "frame_hash": hashlib.sha256(b"{}").hexdigest(),
                "host_observed": True,
                "client_delivered": delivered,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "frame": {},
            })

    def snapshot(self, after_sequence: int = 0) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(row) for row in self._rows if int(row["sequence"]) > after_sequence]

    def outbound_for(self, request_id: str) -> dict[str, Any] | None:
        with self._lock:
            return next((dict(row) for row in self._rows
                         if row.get("direction") == "outbound" and row.get("request_id") == request_id), None)

    def response_for(self, request_id: str) -> dict[str, Any] | None:
        with self._lock:
            outbound = self.outbound_for(request_id)
            if outbound is None:
                return None
            wire_id = outbound.get("wire_id")
            for row in self._rows:
                if row.get("direction") == "inbound" and row.get("wire_id") == wire_id and "id" in row.get("frame", {}):
                    return dict(row["frame"])
            return None

    def request_matches(self, request_id: str, frame: dict[str, Any]) -> bool:
        outbound = self.outbound_for(request_id)
        return outbound is None or outbound.get("payload_hash") == hashlib.sha256(_canonical(frame)).hexdigest()

    def verify(self) -> dict[str, Any]:
        previous = None
        with self._lock:
            for expected_sequence, row in enumerate(self._rows, 1):
                material = dict(row)
                event_hash = material.pop("event_hash", None)
                if material.get("sequence") != expected_sequence or material.get("previous_hash") != previous:
                    return {"valid": False, "last_sequence": expected_sequence - 1}
                if hashlib.sha256(_canonical(material)).hexdigest() != event_hash:
                    return {"valid": False, "last_sequence": expected_sequence - 1}
                previous = event_hash
            return {"valid": True, "last_sequence": len(self._rows), "last_hash": previous}

    def summary(self) -> dict[str, Any]:
        with self._lock:
            return {
                **self.verify(),
                "host_request_count": sum(row.get("direction") == "outbound" and row.get("wire_id") is not None for row in self._rows),
                "host_response_count": sum(row.get("direction") == "inbound" and row.get("wire_id") is not None for row in self._rows),
                "dropped_response_count": sum(row.get("direction") == "broker" and row.get("client_delivered") is False for row in self._rows),
            }


class _BrokerTcpServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


class _Handler(socketserver.StreamRequestHandler):
    def _send(self, payload: dict[str, Any]) -> None:
        self.wfile.write(_canonical(payload) + b"\n")
        self.wfile.flush()

    def handle(self) -> None:
        service: BrokerService = self.server.service  # type: ignore[attr-defined]
        try:
            hello = json.loads(self.rfile.readline())
            if hello.get("op") != "hello" or hello.get("token") != service.token:
                self._send({"op": "error", "error": "unauthorized"})
                return
            connection_id = str(hello.get("connection_id") or "unknown")
            self._send({"op": "hello", "broker_id": service.broker_id})
            command_line = self.rfile.readline()
            if not command_line:
                return
            command = json.loads(command_line)
            response = service.handle_command(command, connection_id)
            if response is not None:
                self._send(response)
        except (OSError, ValueError, json.JSONDecodeError, AppServerProtocolError):
            return


class BrokerService:
    """Owns the app-server process while controller clients reconnect."""

    def __init__(self, process: Any, schema_root: Path, journal_path: Path, *, token: str,
                 host: str = "127.0.0.1", port: int = 0, host_response_timeout: float = 120.0) -> None:
        self.process = process
        self.token = token
        self.broker_id = hashlib.sha256(f"{os.getpid()}:{time.time_ns()}".encode()).hexdigest()[:24]
        self.journal = DurableWireJournal(journal_path)
        self.schemas = SchemaRegistry(schema_root)
        self.transport = JsonRpcTransport(
            process, self.schemas, response_timeout=host_response_timeout, spool=self.journal,
        )
        self.server = _BrokerTcpServer((host, port), _Handler)
        self.server.service = self  # type: ignore[attr-defined]
        self._thread: threading.Thread | None = None
        self._request_locks: dict[str, threading.Lock] = {}
        self._locks_guard = threading.Lock()
        self.shutdown_requested = threading.Event()

    @property
    def endpoint(self) -> tuple[str, int]:
        host, port = self.server.server_address[:2]
        return str(host), int(port)

    def start(self) -> None:
        if self._thread is not None:
            raise RuntimeError("broker already started")
        self._thread = threading.Thread(target=self.server.serve_forever, name="ds-lite-fault-broker", daemon=True)
        self._thread.start()

    def _request_lock(self, request_id: str) -> threading.Lock:
        with self._locks_guard:
            return self._request_locks.setdefault(request_id, threading.Lock())

    def handle_command(self, command: dict[str, Any], connection_id: str) -> dict[str, Any] | None:
        operation = command.get("op")
        if operation == "snapshot":
            return {"op": "snapshot", "rows": self.journal.snapshot(int(command.get("after_sequence", 0)))}
        if operation == "notify":
            self.transport.notify(str(command["method"]), command.get("params"))
            return {"op": "ack"}
        if operation == "status":
            return {
                "op": "status", "broker_id": self.broker_id,
                "next_wire_request_id": self.transport.next_request_id,
                "journal": self.journal.summary(),
            }
        if operation == "shutdown":
            self.shutdown_requested.set()
            return {"op": "ack"}
        if operation != "rpc":
            return {"op": "error", "error": "unsupported-operation"}
        request_id = str(command["request_id"])
        wire_id = int(command["wire_request_id"])
        method = str(command["method"])
        params = command.get("params")
        if not isinstance(params, dict):
            return {"op": "error", "error": "params-must-be-object"}
        frame = {"id": wire_id, "method": method, "params": params}
        with self._request_lock(request_id):
            if not self.journal.request_matches(request_id, frame):
                return {"op": "error", "error": "request-integrity-conflict"}
            response = self.journal.response_for(request_id)
            if response is None and self.journal.outbound_for(request_id) is not None:
                return {"op": "ambiguous", "error": "host-response-not-observed"}
            if response is None:
                self.journal.register_request(wire_id, request_id, connection_id)
                try:
                    response = self.transport.request(method, params, wire_request_id=wire_id)
                except AppServerResponseTimeout:
                    return {"op": "ambiguous", "error": "host-response-timeout"}
                except AppServerClosed:
                    return {"op": "error", "error": "host-closed"}
            if command.get("drop_response") is True:
                self.journal.mark_delivery(wire_id, connection_id, delivered=False)
                return None
            self.journal.mark_delivery(wire_id, connection_id, delivered=True)
            return {"op": "response", "frame": response, "replayed": self.journal.outbound_for(request_id) is not None}

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=2)


class BrokerClientTransport:
    """JsonRpcTransport-compatible client that reconnects for every operation."""

    def __init__(self, endpoint: tuple[str, int], token: str, schemas: SchemaRegistry, *,
                 response_timeout: float = 30.0, connection_id: str | None = None) -> None:
        self.endpoint = endpoint
        self.token = token
        self.schemas = schemas
        self.response_timeout = response_timeout
        self.connection_id = connection_id or hashlib.sha256(f"{os.getpid()}:{time.time_ns()}".encode()).hexdigest()[:20]
        self._next_request_id: int | None = None
        self._drop_methods: set[str] = set()

    @property
    def next_request_id(self) -> int:
        if self._next_request_id is None:
            status = self.status()
            self._next_request_id = int(status["next_wire_request_id"])
        return self._next_request_id

    @next_request_id.setter
    def next_request_id(self, value: int) -> None:
        self._next_request_id = value

    def drop_next_response(self, method: str) -> None:
        self._drop_methods.add(method)

    def _call(self, command: dict[str, Any]) -> dict[str, Any]:
        try:
            with socket.create_connection(self.endpoint, timeout=self.response_timeout) as sock:
                sock.settimeout(self.response_timeout)
                with sock.makefile("rb") as reader, sock.makefile("wb") as writer:
                    writer.write(_canonical({"op": "hello", "token": self.token, "connection_id": self.connection_id}) + b"\n")
                    writer.flush()
                    hello_line = reader.readline()
                    if not hello_line:
                        raise AppServerClosed("broker-closed-before-handshake")
                    hello = json.loads(hello_line)
                    if hello.get("error") == "unauthorized":
                        raise PermissionError("broker-token-rejected")
                    writer.write(_canonical(command) + b"\n")
                    writer.flush()
                    line = reader.readline()
                    if not line:
                        raise AppServerClosed("broker-response-dropped-or-closed")
                    return json.loads(line)
        except socket.timeout as exc:
            raise AppServerResponseTimeout("broker-response-timeout") from exc

    def request(self, method: str, params: dict[str, Any], *, wire_request_id: int | None = None,
                logical_request_id: str | None = None) -> dict[str, Any]:
        self.schemas.validate(method, params)
        wire_id = self.next_request_id if wire_request_id is None else wire_request_id
        self.next_request_id = max(self.next_request_id, wire_id + 1)
        request_id = logical_request_id or f"wire:{wire_id}:{method}"
        drop = method in self._drop_methods
        self._drop_methods.discard(method)
        result = self._call({
            "op": "rpc", "request_id": request_id, "wire_request_id": wire_id,
            "method": method, "params": params, "drop_response": drop,
        })
        if result.get("op") == "response" and isinstance(result.get("frame"), dict):
            return result["frame"]
        if result.get("op") == "ambiguous":
            raise AppServerResponseTimeout(str(result.get("error")))
        raise AppServerProtocolError(str(result.get("error", "broker-protocol-error")))

    def notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        result = self._call({"op": "notify", "method": method, "params": params})
        if result.get("op") != "ack":
            raise AppServerProtocolError("broker-notification-rejected")

    def snapshot(self, after_sequence: int = 0) -> list[dict[str, Any]]:
        result = self._call({"op": "snapshot", "after_sequence": after_sequence})
        rows = result.get("rows")
        if not isinstance(rows, list):
            raise AppServerProtocolError("broker-snapshot-invalid")
        return [row for row in rows if isinstance(row, dict)]

    def status(self) -> dict[str, Any]:
        return self._call({"op": "status"})

    def shutdown(self) -> None:
        result = self._call({"op": "shutdown"})
        if result.get("op") != "ack":
            raise AppServerProtocolError("broker-shutdown-rejected")

    @property
    def notifications(self) -> list[dict[str, Any]]:
        return [dict(row["frame"]) for row in self.snapshot()
                if row.get("direction") == "inbound"
                and isinstance(row.get("frame"), dict)
                and "method" in row["frame"] and "id" not in row["frame"]]

    def wait_for_notification(self, predicate: Any, *, timeout: float) -> dict[str, Any] | None:
        deadline = time.monotonic() + timeout
        while True:
            for notification in self.notifications:
                if predicate(notification):
                    return notification
            if time.monotonic() >= deadline:
                return None
            time.sleep(min(0.05, max(0.0, deadline - time.monotonic())))

    @property
    def waiter_count(self) -> int:
        return 0


class BrokerAppServerAdapter(AppServerAdapter):
    """AppServerAdapter facade backed by a reconnectable broker endpoint."""

    def __init__(self, endpoint: tuple[str, int], token: str, schema_root: Path, *,
                 response_timeout: float = 30.0, connection_id: str | None = None) -> None:
        self.schemas = SchemaRegistry(schema_root)
        self.transport = BrokerClientTransport(
            endpoint, token, self.schemas, response_timeout=response_timeout, connection_id=connection_id,
        )

    def _request(self, method: str, params: dict[str, Any], request_id: str):
        wire_id = self.transport.next_request_id
        response = self.transport.request(
            method, params, wire_request_id=wire_id, logical_request_id=request_id,
        )
        return self._observation(method, request_id, wire_id, response)

    def _observation(self, method: str, request_id: str, wire_id: int, response: dict[str, Any]):
        from .app_server import RpcObservation
        return RpcObservation(
            method, request_id, wire_id, response,
            self._thread_id(response), self._turn_id(response), "acknowledged",
        )

    def start_turn(self, thread_id: str, input_items: list[dict[str, Any]], *, request_id: str,
                   wire_request_id: int | None = None, model: str | None = None):
        wire_id = self.transport.next_request_id if wire_request_id is None else wire_request_id
        params: dict[str, Any] = {"threadId": thread_id, "input": input_items}
        if model is not None:
            params["model"] = model
        response = self.transport.request(
            "turn/start", params,
            wire_request_id=wire_id, logical_request_id=request_id,
        )
        return self._observation("turn/start", request_id, wire_id, response)

    def reconcile_request(self, request_id: str, thread_id: str):
        """Resolve one logical request without considering unrelated turns in the thread."""
        from .app_server import RpcObservation

        rows = self.transport.snapshot()
        responses = [row for row in rows
                     if row.get("direction") == "inbound"
                     and row.get("request_id") == request_id
                     and isinstance(row.get("frame"), dict)
                     and "id" in row["frame"]]
        if len(responses) != 1:
            return RpcObservation("turn/start", request_id, 0, None, thread_id, None, "ambiguous")
        row = responses[0]
        response = row["frame"]
        turn_id = self._turn_id(response)
        wire_id = int(row.get("wire_id") or 0)
        if turn_id is None:
            return RpcObservation("turn/start", request_id, wire_id, response, thread_id, None, "ambiguous")
        matching = [candidate for candidate in rows
                    if candidate.get("direction") == "inbound"
                    and isinstance(candidate.get("frame"), dict)
                    and candidate["frame"].get("method") in {"turn/completed", "turn/failed"}
                    and _identity(candidate["frame"]) == (thread_id, turn_id)]
        disposition = self._turn_disposition(matching[-1]["frame"]) if matching else "acknowledged"
        witness = matching[-1]["frame"] if matching else response
        return RpcObservation("turn/start", request_id, wire_id, witness, thread_id, turn_id, disposition)

    def reconcile_archive(self, request_id: str, thread_id: str):
        from .app_server import RpcObservation

        rows = self.transport.snapshot()
        responses = [row for row in rows
                     if row.get("direction") == "inbound"
                     and row.get("request_id") == request_id
                     and isinstance(row.get("frame"), dict)
                     and "id" in row["frame"]]
        if len(responses) != 1:
            return RpcObservation("thread/archive", request_id, 0, None, thread_id, None, "ambiguous")
        archived = self.list_threads(
            {"archived": True, "limit": 100}, request_id=f"{request_id}:list-archived",
        )
        active = self.list_threads(
            {"archived": False, "limit": 100}, request_id=f"{request_id}:list-active",
        )

        def contains(observation: Any) -> bool:
            result = observation.response.get("result") if observation.response else None
            data = result.get("data") if isinstance(result, dict) else None
            return isinstance(data, list) and any(
                isinstance(item, dict) and item.get("id") == thread_id for item in data
            )

        archived_present = contains(archived)
        active_present = contains(active)
        disposition = "terminal" if archived_present and not active_present else "ambiguous"
        return RpcObservation(
            "thread/archive", request_id, int(responses[0].get("wire_id") or 0),
            responses[0]["frame"], thread_id, None, disposition,
        )


def _codex_command(codex_bin: Path) -> list[str]:
    if os.name == "nt" and codex_bin.suffix.casefold() == ".cmd":
        return ["cmd.exe", "/d", "/s", "/c", f'"{codex_bin}" app-server']
    return [str(codex_bin), "app-server"]


def _broker_environment(home: Path, *, ambient_home: bool) -> dict[str, str]:
    environment = dict(os.environ)
    if ambient_home:
        # Resolve the user's normal Codex home without inspecting or copying credentials.
        environment.pop("CODEX_HOME", None)
    else:
        environment["CODEX_HOME"] = str(home.resolve())
    return environment


def serve_broker(*, codex_bin: Path, home: Path, schema_root: Path, journal_path: Path,
                 ready_file: Path, host_response_timeout: float = 120.0,
                 ambient_home: bool = False) -> int:
    """Run the foreground broker and publish one exclusive-create readiness file."""
    if (not ambient_home and home.exists()) or ready_file.exists() or journal_path.exists():
        raise FileExistsError("broker home, journal, and ready file must be new")
    if not ambient_home:
        home.mkdir(parents=True, exist_ok=False)
    journal_path.parent.mkdir(parents=True, exist_ok=True)
    token = secrets.token_urlsafe(32)
    process = subprocess.Popen(
        _codex_command(codex_bin.resolve()), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL, text=True, encoding="utf-8",
        env=_broker_environment(home, ambient_home=ambient_home),
    )
    service = BrokerService(
        process, schema_root, journal_path, token=token,
        host_response_timeout=host_response_timeout,
    )
    service.start()
    ready = {
        "schema_version": "ds-lite.fault-broker-ready.v1",
        "broker_id": service.broker_id,
        "broker_pid": os.getpid(),
        "app_server_pid": process.pid,
        "host": service.endpoint[0],
        "port": service.endpoint[1],
        "token": token,
        "journal": str(journal_path.resolve()),
        "home_mode": "ambient" if ambient_home else "isolated",
    }
    metadata = {
        "schema_version": "ds-lite.fault-broker-metadata.v1",
        "broker_id": service.broker_id,
        "broker_pid": os.getpid(),
        "app_server_pid": process.pid,
        "journal": journal_path.name,
        "home_mode": "ambient" if ambient_home else "isolated",
    }
    metadata_file = journal_path.parent / "broker-metadata.json"
    with metadata_file.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(metadata, handle, ensure_ascii=True, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    ready_file.parent.mkdir(parents=True, exist_ok=True)
    with ready_file.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(ready, handle, ensure_ascii=True, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    try:
        while not service.shutdown_requested.wait(0.1):
            if process.poll() is not None:
                return 2
        return 0
    finally:
        service.close()
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
