from __future__ import annotations

from pathlib import Path
from typing import Any

from .evidence import canonical_hash, write_once
from .errors import IntegrityIncident
from .store import ControlStore


class GateDecisionEngine:
    def __init__(self, store: ControlStore, receipt_root: Path) -> None:
        self.store = store
        self.receipt_root = receipt_root.resolve()

    def decide(
        self, work_item_id: str, evidence_set_id: str, review_id: str, *,
        owner_id: str, fence_epoch: int, candidate_digest: str | None = None,
    ) -> dict[str, Any]:
        if candidate_digest is not None and (
            len(candidate_digest) != 64
            or any(character not in "0123456789abcdef" for character in candidate_digest.lower())
        ):
            raise ValueError("candidate digest must be a SHA-256 value")
        row = self.store.connection.execute(
            "SELECT e.manifest_hash,v.verifier_id,v.status,r.verdict,r.post_manifest_hash,"
            "r.sidecar_receipt_id FROM evidence_sets e JOIN verifier_runs v "
            "ON v.evidence_set_id=e.evidence_set_id JOIN review_requests q "
            "ON q.verifier_id=v.verifier_id JOIN review_results r ON r.review_id=q.review_id "
            "WHERE e.evidence_set_id=? AND e.work_item_id=? AND q.review_id=?",
            (evidence_set_id, work_item_id, review_id),
        ).fetchone()
        if row is None:
            raise ValueError("verifier and review result are required")
        incidents = int(self.store.connection.execute(
            "SELECT COUNT(*) FROM integrity_incidents WHERE resolved_at IS NULL"
        ).fetchone()[0])
        status = "passed" if row[2] == "passed" and row[3] == "accept" and row[0] == row[4] and incidents == 0 else "blocked"
        input_digest = canonical_hash([
            evidence_set_id, row[0], row[1], review_id, row[5], incidents,
            candidate_digest,
        ])
        decision_id = f"gate-decision-{canonical_hash([work_item_id, evidence_set_id])[:32]}"
        receipt_id = decision_id
        existing = self.store.connection.execute(
            "SELECT status,input_digest,receipt_id FROM gate_decisions WHERE decision_id=?",
            (decision_id,),
        ).fetchone()
        expected = (status, input_digest, receipt_id)
        if existing is not None:
            if tuple(existing) != expected:
                raise IntegrityIncident("gate decision identity conflict")
            import json
            path = self.receipt_root / f"{receipt_id}.json"
            try:
                saved = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise IntegrityIncident("gate decision receipt is missing or invalid") from exc
            if (saved.get("decision_id"), saved.get("status"), saved.get("input_digest")) != (
                decision_id, status, input_digest,
            ):
                raise IntegrityIncident("gate decision receipt content conflict")
            return saved
        receipt = {
            "schema_version": "ds-lite.gate-decision.v1",
            "receipt_id": receipt_id,
            "decision_id": decision_id,
            "work_item_id": work_item_id,
            "evidence_set_id": evidence_set_id,
            "verifier_id": str(row[1]),
            "review_id": review_id,
            "status": status,
            "input_digest": input_digest,
            "candidate_digest": candidate_digest,
            "unresolved_integrity_incidents": incidents,
            "previous_receipt_hash": self.store.latest_receipt_hash(),
        }
        receipt["receipt_hash"] = canonical_hash(receipt)
        path = self.receipt_root / f"{receipt_id}.json"
        content_hash = write_once(path, receipt)
        self.store.connection.execute("BEGIN IMMEDIATE")
        try:
            self.store._check_fence(work_item_id, owner_id, fence_epoch)
            existing = self.store.connection.execute(
                "SELECT status,input_digest,receipt_id FROM gate_decisions WHERE decision_id=?",
                (decision_id,),
            ).fetchone()
            expected = (status, input_digest, receipt_id)
            if existing is not None and tuple(existing) != expected:
                raise IntegrityIncident("gate decision identity conflict")
            self.store.connection.execute(
                "INSERT OR IGNORE INTO gate_decisions(decision_id,work_item_id,evidence_set_id,verifier_id,"
                "review_id,status,input_digest,receipt_id,owner_id,fence_epoch,created_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (decision_id, work_item_id, evidence_set_id, row[1], review_id, status,
                 input_digest, receipt_id, owner_id, fence_epoch, self.store._stamp(self.store._now())),
            )
            self.store.connection.execute(
                "INSERT OR IGNORE INTO receipt_index(receipt_id,entity_id,path,content_hash,previous_hash,"
                "owner_id,fence_epoch,entity_kind,work_item_id) VALUES(?,?,?,?,?,?,?,?,?)",
                (receipt_id, decision_id, path.name, content_hash, receipt["previous_receipt_hash"],
                 owner_id, fence_epoch, "gate-decision", work_item_id),
            )
            self.store.connection.commit()
        except Exception:
            self.store.connection.rollback()
            raise
        return receipt


class StrictReleaseAggregate:
    def __init__(self, store: ControlStore, receipt_root: Path) -> None:
        self.store = store
        self.receipt_root = receipt_root.resolve()

    def decide(self, job_id: str, profile: dict[str, Any]) -> dict[str, Any]:
        if profile.get("schema_version") != "ds-lite.release-profile.v1":
            raise ValueError("unsupported release profile")
        required = profile.get("required_gates")
        if not isinstance(required, list) or not all(isinstance(item, str) and item for item in required):
            raise ValueError("required_gates must be a list of ids")
        decision_rows = {
            str(row[0]): (str(row[1]), str(row[2]))
            for row in self.store.connection.execute(
                "SELECT work_item_id,status,receipt_id FROM gate_decisions WHERE work_item_id IN ("
                + ",".join("?" for _ in required) + ")",
                tuple(required),
            ).fetchall()
        } if required else {}
        missing = [gate for gate in required if gate not in decision_rows]
        nonpassing = [
            gate for gate in required
            if gate in decision_rows and decision_rows[gate][0] != "passed"
        ]
        candidate_digest = profile.get("candidate_digest")
        if candidate_digest is not None and (
            not isinstance(candidate_digest, str) or len(candidate_digest) != 64
            or any(character not in "0123456789abcdef" for character in candidate_digest.lower())
        ):
            raise ValueError("candidate digest must be a SHA-256 value")
        candidate_mismatches: list[str] = []
        if candidate_digest is not None:
            import hashlib
            import json
            for gate in required:
                if gate not in decision_rows:
                    continue
                receipt_id = decision_rows[gate][1]
                indexed = self.store.connection.execute(
                    "SELECT path,content_hash FROM receipt_index WHERE receipt_id=? AND entity_kind='gate-decision'",
                    (receipt_id,),
                ).fetchone()
                if indexed is None:
                    candidate_mismatches.append(gate)
                    continue
                path = self.receipt_root / str(indexed[0])
                try:
                    content = path.read_bytes()
                    receipt = json.loads(content.decode("utf-8"))
                except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                    candidate_mismatches.append(gate)
                    continue
                if (
                    hashlib.sha256(content).hexdigest() != str(indexed[1])
                    or receipt.get("work_item_id") != gate
                    or receipt.get("candidate_digest") != candidate_digest
                ):
                    candidate_mismatches.append(gate)
        unresolved = int(self.store.connection.execute(
            "SELECT COUNT(*) FROM integrity_incidents WHERE resolved_at IS NULL"
        ).fetchone()[0])
        allowed = not missing and not nonpassing and not candidate_mismatches and unresolved == 0
        return {
            "schema_version": "ds-lite.release-decision.v1",
            "job_id": job_id,
            "profile_id": profile.get("profile_id"),
            "fixture_only": bool(profile.get("fixture_only", False)),
            "status": "allowed" if allowed else "blocked",
            "required_gates": list(required),
            "missing_gates": missing,
            "nonpassing_gates": nonpassing,
            "candidate_digest": candidate_digest,
            "candidate_mismatch_gates": candidate_mismatches,
            "unresolved_integrity_incidents": unresolved,
            "release_allowed": bool(allowed),
        }

    def materialize(
        self, job_id: str, profile: dict[str, Any], *, owner_id: str, fence_epoch: int,
    ) -> dict[str, Any]:
        if bool(profile.get("fixture_only", False)):
            raise ValueError("fixture release profiles cannot be materialized")
        decision = self.decide(job_id, profile)
        profile_id = str(profile.get("profile_id") or "")
        if not profile_id:
            raise ValueError("release profile_id is required")
        profile_hash = canonical_hash(profile)
        required_digest = canonical_hash(decision["required_gates"])
        blockers = {
            "missing_gates": decision["missing_gates"],
            "nonpassing_gates": decision["nonpassing_gates"],
            "candidate_mismatch_gates": decision["candidate_mismatch_gates"],
            "unresolved_integrity_incidents": decision["unresolved_integrity_incidents"],
        }
        blockers_digest = canonical_hash(blockers)
        input_digest = canonical_hash({
            "job_id": job_id,
            "profile_hash": profile_hash,
            "required_gates_digest": required_digest,
            "blockers_digest": blockers_digest,
            "status": decision["status"],
        })
        decision_id = f"release-decision-{canonical_hash([job_id, profile_id, input_digest])[:32]}"
        receipt_id = decision_id
        existing = self.store.connection.execute(
            "SELECT receipt_id FROM release_decisions WHERE decision_id=?", (decision_id,)
        ).fetchone()
        if existing is not None:
            path = self.receipt_root / f"{existing[0]}.json"
            import json
            return json.loads(path.read_text(encoding="utf-8"))
        receipt = {
            **decision,
            "receipt_id": receipt_id,
            "decision_id": decision_id,
            "profile_hash": profile_hash,
            "required_gates_digest": required_digest,
            "input_digest": input_digest,
            "blockers_digest": blockers_digest,
            "previous_receipt_hash": self.store.latest_receipt_hash(),
        }
        receipt["receipt_hash"] = canonical_hash(receipt)
        path = self.receipt_root / f"{receipt_id}.json"
        content_hash = write_once(path, receipt)
        self.store.connection.execute("BEGIN IMMEDIATE")
        try:
            self.store._check_fence(job_id, owner_id, fence_epoch)
            stored_profile = self.store.connection.execute(
                "SELECT profile_hash,required_gates_digest,fixture_only FROM release_profiles "
                "WHERE profile_id=?", (profile_id,)
            ).fetchone()
            expected_profile = (profile_hash, required_digest, 0)
            if stored_profile is not None and tuple(stored_profile) != expected_profile:
                raise IntegrityIncident("release profile identity conflict")
            self.store.connection.execute(
                "INSERT OR IGNORE INTO release_profiles(profile_id,profile_hash,required_gates_digest,"
                "fixture_only,created_at) VALUES(?,?,?,?,?)",
                (profile_id, profile_hash, required_digest, 0,
                 self.store._stamp(self.store._now())),
            )
            stored_decision = self.store.connection.execute(
                "SELECT job_id,profile_id,status,release_allowed,input_digest,blockers_digest,receipt_id "
                "FROM release_decisions WHERE decision_id=?", (decision_id,)
            ).fetchone()
            expected_decision = (
                job_id, profile_id, decision["status"], int(decision["release_allowed"]),
                input_digest, blockers_digest, receipt_id,
            )
            if stored_decision is not None and tuple(stored_decision) != expected_decision:
                raise IntegrityIncident("release decision identity conflict")
            self.store.connection.execute(
                "INSERT OR IGNORE INTO release_decisions(decision_id,job_id,profile_id,status,"
                "release_allowed,input_digest,blockers_digest,receipt_id,created_at) "
                "VALUES(?,?,?,?,?,?,?,?,?)",
                (decision_id, job_id, profile_id, decision["status"],
                 int(decision["release_allowed"]), input_digest, blockers_digest,
                 receipt_id, self.store._stamp(self.store._now())),
            )
            self.store.connection.execute(
                "INSERT OR IGNORE INTO receipt_index(receipt_id,entity_id,path,content_hash,previous_hash,"
                "owner_id,fence_epoch,entity_kind,work_item_id) VALUES(?,?,?,?,?,?,?,?,NULL)",
                (receipt_id, decision_id, path.name, content_hash,
                 receipt["previous_receipt_hash"], owner_id, fence_epoch, "release-decision"),
            )
            self.store.connection.commit()
        except Exception:
            self.store.connection.rollback()
            raise
        return receipt


__all__ = ["GateDecisionEngine", "StrictReleaseAggregate"]
