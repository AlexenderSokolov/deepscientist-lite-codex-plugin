from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .evidence import EvidenceError, canonical_hash, file_hash, write_once
from .errors import IntegrityIncident
from .store import ControlStore


class DeterministicVerifier:
    def __init__(self, store: ControlStore, receipt_root: Path) -> None:
        self.store = store
        self.receipt_root = receipt_root.resolve()

    def verify(
        self, work_item_id: str, evidence_set_id: str, policy: dict[str, Any], *,
        owner_id: str, fence_epoch: int,
    ) -> dict[str, Any]:
        row = self.store.connection.execute(
            "SELECT artifact_root,manifest_hash,policy_hash,evidence_class FROM evidence_sets "
            "WHERE evidence_set_id=? AND work_item_id=?",
            (evidence_set_id, work_item_id),
        ).fetchone()
        if row is None:
            raise EvidenceError("unknown evidence set")
        policy_hash = canonical_hash(policy)
        if policy_hash != row[2]:
            raise IntegrityIncident("verification policy differs from frozen evidence")
        checks: list[dict[str, Any]] = []
        check_codes: list[str] = []
        artifact_root = Path(str(row[0]))
        passed = True
        for requirement in policy["required_artifacts"]:
            relative = requirement["path"]
            member = self.store.connection.execute(
                "SELECT schema_version,content_hash FROM evidence_members "
                "WHERE evidence_set_id=? AND relative_path=?",
                (evidence_set_id, relative),
            ).fetchone()
            path = artifact_root / Path(relative)
            valid = bool(member is not None and path.is_file() and file_hash(path) == member[1])
            payload: Any = None
            if valid and path.suffix.lower() == ".json":
                payload = json.loads(path.read_text(encoding="utf-8-sig"))
                expected_schema = requirement.get("schema_version")
                if expected_schema is not None:
                    valid = isinstance(payload, dict) and payload.get("schema_version") == expected_schema
                required_fields = requirement.get("required_fields", {})
                valid = valid and isinstance(payload, dict) and all(
                    payload.get(key) == value for key, value in required_fields.items()
                )
                if any(key in payload for key in ("passed", "gate_passed", "release_allowed")):
                    check_codes.append("protected-claim-ignored")
            checks.append({"path": relative, "passed": bool(valid)})
            passed = passed and bool(valid)
        check_codes.extend("artifact-valid" if item["passed"] else "artifact-invalid" for item in checks)
        verifier_id = f"verifier-{canonical_hash([evidence_set_id, policy_hash])[:32]}"
        receipt_id = verifier_id
        checks_hash = canonical_hash(checks)
        existing = self.store.connection.execute(
            "SELECT status,checks_hash,receipt_id FROM verifier_runs WHERE verifier_id=?",
            (verifier_id,),
        ).fetchone()
        expected = ("passed" if passed else "blocked", checks_hash, receipt_id)
        if existing is not None:
            if tuple(existing) != expected:
                raise IntegrityIncident("verifier identity conflict")
            receipt_path = self.receipt_root / f"{receipt_id}.json"
            try:
                saved = json.loads(receipt_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise IntegrityIncident("verifier receipt is missing or invalid") from exc
            if (saved.get("verifier_id"), saved.get("status"),
                    canonical_hash(saved.get("checks"))) != (verifier_id, expected[0], checks_hash):
                raise IntegrityIncident("verifier receipt content conflict")
            return saved
        receipt = {
            "schema_version": "ds-lite.verifier-receipt.v1",
            "receipt_id": receipt_id,
            "verifier_id": verifier_id,
            "work_item_id": work_item_id,
            "evidence_set_id": evidence_set_id,
            "manifest_hash": str(row[1]),
            "policy_hash": policy_hash,
            "status": "passed" if passed else "blocked",
            "checks": checks,
            "check_codes": sorted(set(check_codes)),
            "previous_receipt_hash": self.store.latest_receipt_hash(),
        }
        receipt["receipt_hash"] = canonical_hash(receipt)
        receipt_path = self.receipt_root / f"{receipt_id}.json"
        content_hash = write_once(receipt_path, receipt)
        self.store.connection.execute("BEGIN IMMEDIATE")
        try:
            self.store._check_fence(work_item_id, owner_id, fence_epoch)
            existing = self.store.connection.execute(
                "SELECT status,checks_hash,receipt_id FROM verifier_runs WHERE verifier_id=?",
                (verifier_id,),
            ).fetchone()
            expected = (receipt["status"], checks_hash, receipt_id)
            if existing is not None and tuple(existing) != expected:
                raise IntegrityIncident("verifier identity conflict")
            self.store.connection.execute(
                "INSERT OR IGNORE INTO verifier_runs(verifier_id,work_item_id,evidence_set_id,policy_hash,"
                "status,checks_hash,receipt_id,owner_id,fence_epoch,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (verifier_id, work_item_id, evidence_set_id, policy_hash, receipt["status"], checks_hash,
                 receipt_id, owner_id, fence_epoch, self.store._stamp(self.store._now())),
            )
            indexed = self.store.connection.execute(
                "SELECT path,content_hash FROM receipt_index WHERE receipt_id=?", (receipt_id,)
            ).fetchone()
            if indexed is not None and tuple(indexed) != (receipt_path.name, content_hash):
                raise IntegrityIncident("verifier receipt index conflict")
            self.store.connection.execute(
                "INSERT OR IGNORE INTO receipt_index(receipt_id,entity_id,path,content_hash,previous_hash,"
                "owner_id,fence_epoch,entity_kind,work_item_id) VALUES(?,?,?,?,?,?,?,?,?)",
                (receipt_id, evidence_set_id, receipt_path.name, content_hash,
                 receipt["previous_receipt_hash"], owner_id, fence_epoch, "verifier", work_item_id),
            )
            self.store.connection.commit()
        except Exception:
            self.store.connection.rollback()
            raise
        return receipt


__all__ = ["DeterministicVerifier"]
