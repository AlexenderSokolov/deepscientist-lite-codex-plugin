from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from .errors import ReceiptConflict
from .store import ControlStore


def _canonical_bytes(payload: dict[str, Any]) -> bytes:
    return (json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


class ReceiptStore:
    def __init__(self, root: Path, domain: ControlStore) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.domain = domain

    def terminal_payload(self, action_id: str, owner_id: str, fence_epoch: int,
                         receipt_id: str | None = None) -> dict[str, Any]:
        action = self.domain.action_context(action_id)
        event = self.domain.terminal_event(action_id)
        existing = self.domain.receipt_index(receipt_id or f"terminal-{action_id}")
        return {
            "schema_version": "ds-lite.receipt.v1",
            "receipt_type": "action_terminal",
            "job_id": action["job_id"],
            "work_item_id": action["work_item_id"],
            "attempt_id": action["attempt_id"],
            "action_id": action_id,
            "workflow_backend": "dbos",
            "workflow_id": action.get("workflow_id") or action_id,
            "workflow_kind": action.get("workflow_kind") or "run_action_v1",
            "workflow_runtime_version": "2.29.0",
            "owner_id": owner_id,
            "fence_epoch": fence_epoch,
            "adapter": "fake-app-server",
            "evidence_class": "fake-host",
            "host_version": "fake-v1",
            "host_schema_digest": "not-applicable-phase1",
            "hook_digest": "not-invoked-phase1",
            "input_state_digest": action["payload_hash"],
            "config_digest": hashlib.sha256(b"ds-lite-phase1-v1").hexdigest(),
            "host_event_id": event["event_id"],
            "host_event_hash": event["witness_hash"],
            "started_at": event["observed_at"],
            "ended_at": event["observed_at"],
            "terminal_status": "completed",
            "failure": None,
            "artifact_refs": [],
            "previous_receipt_hash": (
                existing["previous_hash"] if existing is not None else self.domain.latest_receipt_hash()
            ),
            "redaction_policy_version": "v1",
        }

    def _encoded_receipt(self, receipt_id: str, payload: dict[str, Any]) -> tuple[dict[str, Any], bytes, str]:
        body = dict(payload)
        body["receipt_id"] = receipt_id
        body["receipt_hash"] = hashlib.sha256(_canonical_bytes(body)).hexdigest()
        encoded = _canonical_bytes(body)
        content_hash = hashlib.sha256(encoded).hexdigest()
        return body, encoded, content_hash

    def write_file(self, receipt_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        body, encoded, content_hash = self._encoded_receipt(receipt_id, payload)
        destination = self.root / f"{receipt_id}.json"
        if destination.exists():
            if destination.read_bytes() != encoded:
                raise ReceiptConflict("write-once receipt content differs")
        else:
            with destination.open("xb") as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
        return {"path": str(destination), "content_hash": content_hash, "receipt": body}

    def index_written_file(self, receipt_id: str, payload: dict[str, Any], owner_id: str,
                           fence_epoch: int) -> dict[str, Any]:
        body, encoded, content_hash = self._encoded_receipt(receipt_id, payload)
        destination = self.root / f"{receipt_id}.json"
        if not destination.is_file() or destination.read_bytes() != encoded:
            raise ReceiptConflict("receipt file missing or differs before index")
        self.domain.index_receipt(
            receipt_id=receipt_id, entity_id=str(payload["action_id"]), path=destination.name,
            content_hash=content_hash, previous_hash=payload.get("previous_receipt_hash"),
            owner_id=owner_id, fence_epoch=fence_epoch,
        )
        return {"path": str(destination), "content_hash": content_hash, "receipt": body}

    def write_and_index(self, receipt_id: str, payload: dict[str, Any], owner_id: str,
                        fence_epoch: int) -> dict[str, Any]:
        self.write_file(receipt_id, payload)
        return self.index_written_file(receipt_id, payload, owner_id, fence_epoch)


__all__ = ["ReceiptConflict", "ReceiptStore"]
