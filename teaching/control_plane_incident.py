"""Write-only, redacted receipts for control-plane integrity incidents."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def record_receipt_write_incident(path: Path, *, attempted_receipt_id: str,
                                  target_path: Path | None, stage: str) -> dict[str, Any]:
    """Record an exclusive-create failure without retaining command output or paths."""
    if not attempted_receipt_id:
        raise ValueError("attempted_receipt_id is required")
    if stage not in {"receipt-write", "receipt-fsync", "receipt-index"}:
        raise ValueError("unsupported incident stage")
    receipt = {
        "schema_version": "ds-lite.control-plane-integrity-incident.v1",
        "incident_type": "receipt-write",
        "status": "recorded",
        "failure_layer": "evidence/receipt-write",
        "attempted_receipt_id_sha256": _digest(attempted_receipt_id),
        "target_path_sha256": _digest(str(target_path.resolve())) if target_path is not None else None,
        "target_path_exact_observed": target_path is not None,
        "stage": stage,
        "raw_command_persisted": False,
        "raw_output_persisted": False,
        "retry_same_identity": False,
        "resolution": "freeze-identity-create-new-evidence-identity",
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        json.dump(receipt, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
    return receipt


def record_false_success_incident(path: Path, *, source_receipt_id: str,
                                  source_receipt_sha256: str, reason: str) -> dict[str, Any]:
    """Quarantine a write-once receipt whose verifier was later shown insufficient."""
    if not source_receipt_id or len(source_receipt_sha256) != 64 or not reason:
        raise ValueError("source receipt identity, sha256, and reason are required")
    receipt = {
        "schema_version": "ds-lite.control-plane-integrity-incident.v1",
        "incident_type": "false-success-receipt",
        "status": "recorded",
        "failure_layer": "evidence/verifier",
        "source_receipt_id_sha256": _digest(source_receipt_id),
        "source_receipt_sha256": source_receipt_sha256.casefold(),
        "reason": reason,
        "source_receipt_quarantined": True,
        "source_receipt_overwritten": False,
        "raw_output_persisted": False,
        "resolution": "exclude-and-rerun-with-persisted-state-verifier",
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        json.dump(receipt, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--attempted-receipt-id", required=True)
    parser.add_argument("--target-path", type=Path)
    parser.add_argument(
        "--stage",
        choices=("receipt-write", "receipt-fsync", "receipt-index"),
        default="receipt-write",
    )
    args = parser.parse_args()
    receipt = record_receipt_write_incident(
        args.output.resolve(),
        attempted_receipt_id=args.attempted_receipt_id,
        target_path=args.target_path,
        stage=args.stage,
    )
    print(json.dumps({"status": receipt["status"], "failure_layer": receipt["failure_layer"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
