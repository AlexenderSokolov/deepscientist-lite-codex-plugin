#!/usr/bin/env python3
"""Research Signal Ledger — append-only signal store for DS Lite v6.

A signal is an observation with a source, scope, dependencies, and expiry.
It is not a final fact. The ledger is append-only: signals can be superseded
or retracted but never deleted.

Schema: ds-lite.signal-ledger.v1
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from pathlib import Path
from typing import Any

SIGNAL_LEDGER_SCHEMA = "ds-lite.signal-ledger.v1"
SIGNAL_SCHEMA = "ds-lite.signal.v1"
ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,79}$")
SIGNAL_TYPES = frozenset({
    "novelty-gap", "feasibility-probe", "evidence-found", "evidence-missing",
    "cost-estimate", "risk-flag", "alignment-check", "failure-observed",
    "duplicate-suspected", "boundary-confirmed", "prerequisite-missing",
})
SIGNAL_STATUSES = frozenset({"active", "superseded", "retracted", "expired"})
CONFIDENCE_LEVELS = frozenset({"high", "medium", "low", "unknown"})


class SignalError(RuntimeError):
    pass


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _signal_digest(signal: dict[str, Any]) -> str:
    """Compute a stable SHA-256 digest of a signal's core fields."""
    core = json.dumps({
        "signal_id": signal["signal_id"],
        "signal_type": signal["signal_type"],
        "source_ref": signal["source_ref"],
        "scope": signal["scope"],
        "observation": signal["observation"],
        "confidence": signal["confidence"],
    }, sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(core.encode("utf-8")).hexdigest()


def validate_signal(payload: Any) -> dict[str, Any]:
    """Validate a single signal against ds-lite.signal.v1."""
    if not isinstance(payload, dict):
        raise SignalError("signal must be an object")
    required = {
        "signal_id", "signal_type", "source_ref", "scope", "observation",
        "confidence", "dependencies", "expiry", "status", "created_at",
        "extensions",
    }
    if set(payload) != required:
        raise SignalError(f"signal must contain exactly {', '.join(sorted(required))}")

    signal_id = payload["signal_id"]
    if not isinstance(signal_id, str) or not ID_RE.fullmatch(signal_id):
        raise SignalError("signal_id must match identifier pattern")

    signal_type = payload["signal_type"]
    if signal_type not in SIGNAL_TYPES:
        raise SignalError(f"signal_type must be one of {', '.join(sorted(SIGNAL_TYPES))}")

    source_ref = payload["source_ref"]
    if not isinstance(source_ref, str) or not source_ref.strip():
        raise SignalError("source_ref must be a non-empty string")

    scope = payload["scope"]
    if not isinstance(scope, dict):
        raise SignalError("scope must be an object")
    if not isinstance(scope.get("work_unit_id"), str) or not ID_RE.fullmatch(scope["work_unit_id"]):
        raise SignalError("scope.work_unit_id must be a valid identifier")
    if not isinstance(scope.get("route_node_id"), str) or not scope["route_node_id"].strip():
        raise SignalError("scope.route_node_id must be a non-empty string")

    observation = payload["observation"]
    if not isinstance(observation, str) or not observation.strip():
        raise SignalError("observation must be a non-empty string")

    confidence = payload["confidence"]
    if confidence not in CONFIDENCE_LEVELS:
        raise SignalError(f"confidence must be one of {', '.join(sorted(CONFIDENCE_LEVELS))}")

    dependencies = payload["dependencies"]
    if not isinstance(dependencies, list):
        raise SignalError("dependencies must be a list")
    for dep in dependencies:
        if not isinstance(dep, str) or not dep.strip():
            raise SignalError("each dependency must be a non-empty string")

    expiry = payload["expiry"]
    if not isinstance(expiry, dict):
        raise SignalError("expiry must be an object")
    if expiry.get("type") not in ("never", "on-supersede", "on-condition", "on-time"):
        raise SignalError("expiry.type is invalid")
    if expiry["type"] == "on-time":
        if not isinstance(expiry.get("deadline"), str) or not expiry["deadline"].strip():
            raise SignalError("expiry.deadline must be a non-empty string")

    status = payload["status"]
    if status not in SIGNAL_STATUSES:
        raise SignalError(f"status must be one of {', '.join(sorted(SIGNAL_STATUSES))}")

    if not isinstance(payload["created_at"], str) or not payload["created_at"].strip():
        raise SignalError("created_at must be a non-empty ISO-8601 string")

    if not isinstance(payload["extensions"], dict):
        raise SignalError("extensions must be an object")

    return json.loads(json.dumps(payload))


def create_ledger(ledger_id: str, work_unit_id: str, root: str) -> dict[str, Any]:
    """Create a new signal ledger file."""
    if not ID_RE.fullmatch(ledger_id):
        raise SignalError("ledger_id must match identifier pattern")
    if not ID_RE.fullmatch(work_unit_id):
        raise SignalError("work_unit_id must match identifier pattern")

    ledger_path = Path(root) / "research" / "artifacts" / f"signal-ledger-{ledger_id}.json"
    if ledger_path.exists():
        raise SignalError(f"ledger already exists: {ledger_path}")

    ledger = {
        "schema_version": SIGNAL_LEDGER_SCHEMA,
        "ledger_id": ledger_id,
        "work_unit_id": work_unit_id,
        "signals": [],
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    ledger_path.write_text(json.dumps(ledger, ensure_ascii=True, indent=2), encoding="utf-8")
    return ledger


def append_signal(ledger_path: str, signal: dict[str, Any]) -> dict[str, Any]:
    """Append a validated signal to the ledger."""
    path = Path(ledger_path)
    if not path.exists():
        raise SignalError(f"ledger not found: {path}")

    ledger = json.loads(path.read_text(encoding="utf-8"))
    if ledger.get("schema_version") != SIGNAL_LEDGER_SCHEMA:
        raise SignalError("invalid ledger schema")

    validated = validate_signal(signal)

    # Check for duplicate signal_id
    existing_ids = {s["signal_id"] for s in ledger["signals"]}
    if validated["signal_id"] in existing_ids:
        raise SignalError(f"signal_id '{validated['signal_id']}' already exists in ledger")

    # Compute and attach digest
    validated["signal_digest"] = _signal_digest(validated)

    ledger["signals"].append(validated)
    ledger["updated_at"] = _now_iso()
    path.write_text(json.dumps(ledger, ensure_ascii=True, indent=2), encoding="utf-8")
    return validated


def supersede_signal(ledger_path: str, old_signal_id: str, new_signal_id: str) -> dict[str, Any]:
    """Mark a signal as superseded by another signal."""
    path = Path(ledger_path)
    ledger = json.loads(path.read_text(encoding="utf-8"))

    for signal in ledger["signals"]:
        if signal["signal_id"] == old_signal_id:
            signal["status"] = "superseded"
            signal.setdefault("extensions", {})["superseded_by"] = new_signal_id
            ledger["updated_at"] = _now_iso()
            path.write_text(json.dumps(ledger, ensure_ascii=True, indent=2), encoding="utf-8")
            return signal
    raise SignalError(f"signal '{old_signal_id}' not found in ledger")


def list_signals(ledger_path: str, status: str | None = None) -> list[dict[str, Any]]:
    """List signals in a ledger, optionally filtered by status."""
    path = Path(ledger_path)
    ledger = json.loads(path.read_text(encoding="utf-8"))
    signals = ledger.get("signals", [])
    if status:
        signals = [s for s in signals if s.get("status") == status]
    return signals


def main() -> int:
    parser = argparse.ArgumentParser(description="Research Signal Ledger for DS Lite v6")
    sub = parser.add_subparsers(dest="command", required=True)

    create_parser = sub.add_parser("create")
    create_parser.add_argument("--ledger-id", required=True)
    create_parser.add_argument("--work-unit-id", required=True)
    create_parser.add_argument("--root", required=True)

    append_parser = sub.add_parser("append")
    append_parser.add_argument("--ledger", required=True)
    append_parser.add_argument("--signal", required=True, help="Path to signal JSON file")

    list_parser = sub.add_parser("list")
    list_parser.add_argument("--ledger", required=True)
    list_parser.add_argument("--status", choices=sorted(SIGNAL_STATUSES))

    supersede_parser = sub.add_parser("supersede")
    supersede_parser.add_argument("--ledger", required=True)
    supersede_parser.add_argument("--old-id", required=True)
    supersede_parser.add_argument("--new-id", required=True)

    args = parser.parse_args()
    try:
        if args.command == "create":
            result = create_ledger(args.ledger_id, args.work_unit_id, args.root)
        elif args.command == "append":
            signal = json.loads(Path(args.signal).read_text(encoding="utf-8"))
            result = append_signal(args.ledger, signal)
        elif args.command == "list":
            result = list_signals(args.ledger, getattr(args, "status", None))
        elif args.command == "supersede":
            result = supersede_signal(args.ledger, args.old_id, args.new_id)
        else:
            print(json.dumps({"error": f"unknown command: {args.command}"}))
            return 1
        print(json.dumps(result, ensure_ascii=True, indent=2))
        return 0
    except (SignalError, json.JSONDecodeError, OSError) as exc:
        print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
