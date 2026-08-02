"""Real Codex network-fault probes with content-free proxy evidence."""

from __future__ import annotations

import argparse
import hashlib
import http.server
import json
import os
import select
import socket
import socketserver
import subprocess
import threading
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def _write_once(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=True, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())


def _event_summary(lines: list[str]) -> dict[str, Any]:
    counts: Counter[str] = Counter()
    error_text = ""
    for line in lines:
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(value, dict) or not isinstance(value.get("type"), str):
            continue
        counts[value["type"]] += 1
        if value["type"] in {"error", "turn.failed"}:
            error_text += " " + json.dumps(value, ensure_ascii=True).lower()
    classes = []
    if "429" in error_text or "rate limit" in error_text:
        classes.append("rate-limit")
    if any(marker in error_text for marker in ("500", "502", "503", "504", "service unavailable")):
        classes.append("provider-5xx")
    if "stream disconnected" in error_text or "error sending request" in error_text:
        classes.append("stream-disconnect")
    return {
        "event_type_counts": dict(sorted(counts.items())),
        "error_classes": sorted(set(classes)),
        "raw_output_persisted": False,
    }


class _ProxyServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True


class ConnectDropProxy:
    def __init__(self, min_client_bytes: int = 4096, min_server_bytes: int = 4096,
                 upstream_proxy: str | None = None) -> None:
        self.min_client_bytes = min_client_bytes
        self.min_server_bytes = min_server_bytes
        self.upstream_proxy = upstream_proxy
        self.records: list[dict[str, Any]] = []
        owner = self

        class Handler(socketserver.BaseRequestHandler):
            def handle(self) -> None:
                header = b""
                while b"\r\n\r\n" not in header and len(header) < 65536:
                    chunk = self.request.recv(4096)
                    if not chunk:
                        return
                    header += chunk
                first = header.split(b"\r\n", 1)[0].decode("ascii", "replace")
                parts = first.split()
                if len(parts) < 2 or parts[0].upper() != "CONNECT":
                    return
                host, separator, raw_port = parts[1].rpartition(":")
                if not separator:
                    return
                try:
                    if owner.upstream_proxy:
                        upstream = urllib.parse.urlparse(owner.upstream_proxy)
                        if not upstream.hostname:
                            raise OSError("upstream proxy hostname missing")
                        target = socket.create_connection(
                            (upstream.hostname, upstream.port or 80), timeout=5
                        )
                        target.sendall(
                            f"CONNECT {parts[1]} HTTP/1.1\r\nHost: {parts[1]}\r\n\r\n".encode("ascii")
                        )
                        response = b""
                        while b"\r\n\r\n" not in response and len(response) < 65536:
                            chunk = target.recv(4096)
                            if not chunk:
                                break
                            response += chunk
                        if b" 200 " not in response.split(b"\r\n", 1)[0]:
                            raise OSError("upstream CONNECT rejected")
                    else:
                        target = socket.create_connection((host, int(raw_port)), timeout=5)
                except OSError:
                    try:
                        self.request.sendall(b"HTTP/1.1 502 Bad Gateway\r\n\r\n")
                    except OSError:
                        pass
                    owner.records.append({
                        "target_sha256": hashlib.sha256(parts[1].encode("utf-8")).hexdigest(),
                        "byte_counts": {}, "stream_sha256": {}, "drop_triggered": False,
                        "connect_failed": True, "content_persisted": False,
                    })
                    return
                self.request.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
                sockets = [self.request, target]
                byte_counts = {"client_to_server": 0, "server_to_client": 0}
                digests = {key: hashlib.sha256() for key in byte_counts}
                dropped = False
                try:
                    while True:
                        readable, _, _ = select.select(sockets, [], [], 30)
                        if not readable:
                            break
                        for source in readable:
                            data = source.recv(65536)
                            if not data:
                                return
                            if source is self.request:
                                key, destination = "client_to_server", target
                            else:
                                key, destination = "server_to_client", self.request
                            byte_counts[key] += len(data)
                            digests[key].update(data)
                            destination.sendall(data)
                        if (
                            byte_counts["client_to_server"] >= owner.min_client_bytes
                            and byte_counts["server_to_client"] >= owner.min_server_bytes
                        ):
                            dropped = True
                            break
                finally:
                    target.close()
                    owner.records.append({
                        "target_sha256": hashlib.sha256(parts[1].encode("utf-8")).hexdigest(),
                        "byte_counts": byte_counts,
                        "stream_sha256": {key: value.hexdigest() for key, value in digests.items()},
                        "drop_triggered": dropped,
                        "content_persisted": False,
                    })

        self.server = _ProxyServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    @property
    def endpoint(self) -> str:
        host, port = self.server.server_address[:2]
        return f"http://{host}:{port}"

    def __enter__(self) -> "ConnectDropProxy":
        self.thread.start()
        return self

    def __exit__(self, *_: object) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)


class SyntheticProvider:
    def __init__(self, status: int, retry_after: int | None) -> None:
        self.status = status
        self.retry_after = retry_after
        self.requests: list[dict[str, Any]] = []
        owner = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802
                length = int(self.headers.get("Content-Length", "0"))
                body = self.rfile.read(length)
                owner.requests.append({
                    "path_sha256": hashlib.sha256(self.path.encode("utf-8")).hexdigest(),
                    "body_bytes": len(body), "body_sha256": hashlib.sha256(body).hexdigest(),
                })
                payload = json.dumps({"error": {"type": "synthetic", "message": f"HTTP {owner.status}"}}).encode()
                self.send_response(owner.status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                if owner.retry_after is not None:
                    self.send_header("Retry-After", str(owner.retry_after))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *_: object) -> None:
                return

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    @property
    def base_url(self) -> str:
        host, port = self.server.server_address[:2]
        return f"http://{host}:{port}"

    def __enter__(self) -> "SyntheticProvider":
        self.thread.start()
        return self

    def __exit__(self, *_: object) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)


def _codex_exec(args: argparse.Namespace, home: Path, env: dict[str, str]) -> tuple[int, dict[str, Any]]:
    command = [
        str(args.codex_bin.resolve()), "exec", "--json", "--sandbox", "read-only",
        "--skip-git-repo-check", "-C", str(args.workspace.resolve()),
        "Return exactly PHASE5_NETWORK_OK. Do not use tools.",
    ]
    try:
        completed = subprocess.run(
            command, env=env, capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=args.timeout, check=False,
        )
        lines = completed.stdout.splitlines() + completed.stderr.splitlines()
        return completed.returncode, _event_summary(lines)
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout.decode("utf-8", "replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        stderr = exc.stderr.decode("utf-8", "replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        summary = _event_summary(stdout.splitlines() + stderr.splitlines())
        summary["process_timeout"] = True
        return 124, summary


def evaluate_disconnect_sample(proxy: dict[str, Any], events: dict[str, Any]) -> bool:
    counts = events.get("event_type_counts", {})
    return bool(
        proxy.get("drop_triggered") is True
        and proxy.get("content_persisted") is False
        and counts.get("thread.started") == 1
        and counts.get("turn.started") == 1
        and counts.get("turn.failed") == 1
        and "stream-disconnect" in events.get("error_classes", [])
    )


def run_disconnect_matrix(args: argparse.Namespace) -> dict[str, Any]:
    if args.output.exists():
        raise FileExistsError("network matrix receipt already exists")
    samples = []
    for index in range(args.samples):
        proxies = urllib.request.getproxies()
        upstream_proxy = (
            os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
            or proxies.get("https") or proxies.get("http")
        )
        with ConnectDropProxy(
            args.min_client_bytes, args.min_server_bytes, upstream_proxy=upstream_proxy
        ) as proxy:
            env = os.environ.copy()
            env["CODEX_HOME"] = str(args.codex_home.resolve())
            env["HTTPS_PROXY"] = proxy.endpoint
            env["HTTP_PROXY"] = proxy.endpoint
            env.pop("ALL_PROXY", None)
            env.pop("NO_PROXY", None)
            env.pop("no_proxy", None)
            returncode, events = _codex_exec(args, args.codex_home, env)
        record = next(
            (item for item in proxy.records if item.get("drop_triggered") is True),
            proxy.records[-1] if proxy.records else {
            "drop_triggered": False, "content_persisted": False,
            "byte_counts": {}, "stream_sha256": {}, "target_sha256": None,
            },
        )
        samples.append({
            "sample_id": f"disconnect-{index + 1:02d}",
            "status": "passed" if evaluate_disconnect_sample(record, events) else "failed",
            "process_exit_code": returncode,
            "proxy": record,
            "events": events,
        })
    result = {
        "schema_version": "ds-lite.phase5-network-disconnect.v1",
        "status": "passed" if len(samples) == 10 and all(item["status"] == "passed" for item in samples) else "failed",
        "evidence_class": "real-codex-ambient-provider-loopback-connect-fault",
        "samples": samples,
        "raw_model_output_persisted": False,
        "proxy_decrypted_content": False,
        "release_allowed": False,
    }
    _write_once(args.output, result)
    return result


def _synthetic_home(root: Path, base_url: str) -> Path:
    home = root / "codex-home"
    home.mkdir(parents=True, exist_ok=False)
    config = (
        'model = "gpt-5.6-sol"\nmodel_provider = "custom"\n'
        '[model_providers.custom]\nname = "synthetic"\n'
        f'base_url = {json.dumps(base_url)}\nwire_api = "responses"\n'
        'requires_openai_auth = false\nrequest_max_retries = 0\nstream_max_retries = 0\n'
    )
    (home / "config.toml").write_text(config, encoding="utf-8", newline="\n")
    return home


def run_synthetic(args: argparse.Namespace) -> dict[str, Any]:
    if args.output.exists() or args.runtime.exists():
        raise FileExistsError("synthetic provider paths must be new")
    args.runtime.mkdir(parents=True, exist_ok=False)
    samples = []
    for status, retry_after in ((429, 17), (503, None)):
        sample_root = args.runtime / str(status)
        sample_root.mkdir()
        with SyntheticProvider(status, retry_after) as provider:
            home = _synthetic_home(sample_root, provider.base_url)
            env = os.environ.copy()
            env["CODEX_HOME"] = str(home.resolve())
            for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
                env.pop(key, None)
            env["NO_PROXY"] = "127.0.0.1,localhost"
            returncode, events = _codex_exec(args, home, env)
        expected_class = "rate-limit" if status == 429 else "provider-5xx"
        passed = (
            len(provider.requests) == 1
            and expected_class in events["error_classes"]
            and events["event_type_counts"].get("turn.failed") == 1
            and returncode != 0
        )
        samples.append({
            "status_code": status, "retry_after_seconds": retry_after,
            "status": "passed" if passed else "failed", "request_count": len(provider.requests),
            "request_metadata": provider.requests, "events": events,
            "process_exit_code": returncode,
        })
    result = {
        "schema_version": "ds-lite.phase5-synthetic-provider.v1",
        "status": "passed" if all(item["status"] == "passed" for item in samples) else "failed",
        "evidence_class": "real-codex/synthetic-provider",
        "samples": samples,
        "real_openai_rate_limit_claimed": False,
        "raw_request_or_response_persisted": False,
        "release_allowed": False,
    }
    _write_once(args.output, result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    disconnect = sub.add_parser("disconnect-matrix")
    disconnect.add_argument("--samples", type=int, default=10)
    disconnect.add_argument("--min-client-bytes", type=int, default=4096)
    disconnect.add_argument("--min-server-bytes", type=int, default=4096)
    synthetic = sub.add_parser("synthetic-provider")
    synthetic.add_argument("--runtime", type=Path, required=True)
    for child in (disconnect, synthetic):
        child.add_argument("--codex-bin", type=Path, required=True)
        child.add_argument("--codex-home", type=Path, default=Path.home() / ".codex")
        child.add_argument("--workspace", type=Path, required=True)
        child.add_argument("--output", type=Path, required=True)
        child.add_argument("--timeout", type=float, default=120.0)
    args = parser.parse_args()
    result = run_disconnect_matrix(args) if args.command == "disconnect-matrix" else run_synthetic(args)
    print(json.dumps({"status": result["status"], "evidence_class": result["evidence_class"]}))
    return 0 if result["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
