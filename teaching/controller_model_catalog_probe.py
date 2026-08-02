from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CONTROLLER_ROOT = ROOT / "plugins" / "deepscientist-lite-core" / "controller"
sys.path.insert(0, str(CONTROLLER_ROOT))

from ds_lite_control.app_server import AppServerAdapter
from ds_lite_control.broker import _codex_command


def summarize(response: dict[str, Any]) -> dict[str, Any]:
    result = response.get("result")
    data = result.get("data") if isinstance(result, dict) else None
    if not isinstance(data, list):
        raise RuntimeError("model-catalog-missing-data")
    models = []
    for row in data:
        if not isinstance(row, dict) or not isinstance(row.get("model"), str):
            raise RuntimeError("model-catalog-invalid-row")
        models.append({
            "id": row.get("id"),
            "model": row["model"],
            "display_name": row.get("displayName"),
            "hidden": bool(row.get("hidden")),
            "is_default": bool(row.get("isDefault")),
            "upgrade": row.get("upgrade"),
        })
    canonical = json.dumps(models, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return {
        "models": models,
        "catalog_sha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        "next_cursor_present": bool(result.get("nextCursor")) if isinstance(result, dict) else False,
    }


def _write_once(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=True, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())


def run(args: argparse.Namespace) -> dict[str, Any]:
    ambient_home = bool(getattr(args, "ambient_home", False))
    if args.output.exists() or (not ambient_home and args.home.exists()):
        raise FileExistsError("model catalog probe paths must be new")
    if not ambient_home:
        args.home.mkdir(parents=True, exist_ok=False)
    version = subprocess.run(
        [str(args.codex_bin.resolve()), "--version"], capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=30,
    ).stdout.strip()
    if version != f"codex-cli {args.codex_version}":
        raise RuntimeError("pinned-codex-version-mismatch")
    command = _codex_command(args.codex_bin.resolve())
    if args.proxy_socket is not None:
        command = [str(args.codex_bin.resolve()), "app-server", "proxy", "--sock", args.proxy_socket]
    environment = dict(os.environ)
    if ambient_home:
        # Use the user's normal Codex resolution without inspecting or copying credentials.
        environment.pop("CODEX_HOME", None)
    else:
        environment["CODEX_HOME"] = str(args.home.resolve())
    process: subprocess.Popen[str] | None = None
    try:
        process = subprocess.Popen(
            command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, encoding="utf-8",
            env=environment,
        )
        adapter = AppServerAdapter(process, args.schema_root, response_timeout=30.0)
        adapter.initialize(request_id="phase3-model-catalog:initialize")
        observation = adapter.list_models(
            include_hidden=True, request_id="phase3-model-catalog:model-list",
        )
        if observation.response is None:
            raise RuntimeError("model-catalog-response-missing")
        summary = summarize(observation.response)
        receipt = {
            "schema_version": "ds-lite.codex-model-catalog.v1",
            "codex_version": version,
            "evidence_class": "real-app-server-model-catalog",
            "home_mode": "ambient" if ambient_home else "isolated",
            **summary,
            "release_allowed": False,
        }
        _write_once(args.output, receipt)
        return receipt
    except Exception as error:
        # Keep a durable negative observation without persisting host stderr or model content.
        _write_once(args.output, {
            "schema_version": "ds-lite.codex-model-catalog.v1",
            "codex_version": version,
            "evidence_class": "real-app-server-model-catalog",
            "observation_status": "unobserved",
            "home_mode": "ambient" if ambient_home else "isolated",
            "transport": "proxy" if args.proxy_socket is not None else "child-app-server",
            "proxy_socket_configured": args.proxy_socket is not None,
            "failure_type": type(error).__name__,
            "release_allowed": False,
        })
        raise
    finally:
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--codex-bin", type=Path, required=True)
    parser.add_argument("--schema-root", type=Path, required=True)
    parser.add_argument("--codex-version", required=True)
    parser.add_argument("--proxy-socket")
    parser.add_argument("--ambient-home", action="store_true")
    parser.add_argument("--home", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    result = run(parser.parse_args())
    print(json.dumps({
        "catalog_sha256": result["catalog_sha256"],
        "models": [row["model"] for row in result["models"]],
    }, ensure_ascii=True, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
