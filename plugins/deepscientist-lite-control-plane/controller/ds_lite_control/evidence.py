from __future__ import annotations

import hashlib
import json
import mimetypes
import os
from pathlib import Path, PurePosixPath
from typing import Any

from .errors import IntegrityIncident
from .store import ControlStore


class EvidenceError(ValueError):
    pass


FORBIDDEN_FORMAL_FIELDS = {
    "password", "token", "secret", "api_key", "apikey", "authorization",
    "cookie", "credential", "credentials", "environment", "env", "stderr",
    "raw_stderr", "transcript", "raw_transcript",
}


def _contains_forbidden_field(value: Any) -> bool:
    if isinstance(value, dict):
        return any(
            str(key).lower().replace("-", "_") in FORBIDDEN_FORMAL_FIELDS
            or _contains_forbidden_field(item)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return any(_contains_forbidden_field(item) for item in value)
    return False


def canonical_bytes(payload: dict[str, Any]) -> bytes:
    return (json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def canonical_hash(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_once(path: Path, payload: dict[str, Any]) -> str:
    encoded = canonical_bytes(payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != encoded:
            raise IntegrityIncident("write-once evidence content differs")
    else:
        with path.open("xb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
    return hashlib.sha256(encoded).hexdigest()


def _safe_member(root: Path, relative: str) -> Path:
    posix = PurePosixPath(relative)
    if not relative or posix.is_absolute() or ".." in posix.parts or "\\" in relative:
        raise EvidenceError("artifact path must be relative and contained")
    candidate = root.joinpath(*posix.parts)
    if any(part.is_symlink() for part in (candidate, *candidate.parents) if part != root.parent):
        raise EvidenceError("artifact symlink is forbidden")
    resolved = candidate.resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError as exc:
        raise EvidenceError("artifact path escapes root") from exc
    if not resolved.is_file():
        raise EvidenceError(f"artifact is missing or not a file: {relative}")
    return resolved


class EvidenceManager:
    def __init__(self, store: ControlStore, evidence_root: Path, private_spool_root: Path) -> None:
        self.store = store
        self.evidence_root = evidence_root.resolve()
        self.private_spool_root = private_spool_root.resolve()

    @staticmethod
    def validate_policy(policy: dict[str, Any]) -> dict[str, Any]:
        if policy.get("schema_version") != "ds-lite.gate-policy.v1":
            raise EvidenceError("unsupported gate policy")
        if not isinstance(policy.get("policy_id"), str) or not policy["policy_id"]:
            raise EvidenceError("policy_id is required")
        members = policy.get("required_artifacts")
        if not isinstance(members, list) or not members:
            raise EvidenceError("required_artifacts must be non-empty")
        if policy.get("minimum_evidence_class") not in {"offline", "real-host", "cross-epoch", "independent-review"}:
            raise EvidenceError("unsupported evidence class")
        return policy

    def freeze(
        self,
        job_id: str,
        work_item_id: str,
        artifact_root: Path,
        policy: dict[str, Any],
        *,
        evidence_class: str,
        owner_id: str,
        fence_epoch: int,
    ) -> dict[str, Any]:
        policy = self.validate_policy(policy)
        artifact_root = artifact_root.resolve()
        members: list[dict[str, Any]] = []
        for requirement in policy["required_artifacts"]:
            if not isinstance(requirement, dict) or not isinstance(requirement.get("path"), str):
                raise EvidenceError("artifact requirement must have a path")
            relative = requirement["path"]
            if any(
                part.lower().replace("-", "_").split(".")[0] in FORBIDDEN_FORMAL_FIELDS
                for part in PurePosixPath(relative).parts
            ):
                raise EvidenceError("raw or sensitive artifact path is forbidden")
            path = _safe_member(artifact_root, relative)
            maximum = int(requirement.get("max_size_bytes", 16 * 1024 * 1024))
            if maximum <= 0 or path.stat().st_size > maximum:
                raise EvidenceError(f"artifact exceeds size policy: {relative}")
            schema_version = None
            if path.suffix.lower() == ".json":
                try:
                    value = json.loads(path.read_text(encoding="utf-8-sig"))
                except (OSError, UnicodeError, json.JSONDecodeError) as exc:
                    raise EvidenceError(f"invalid JSON artifact: {relative}") from exc
                if _contains_forbidden_field(value):
                    raise EvidenceError(f"sensitive field is forbidden in formal evidence: {relative}")
                schema_version = value.get("schema_version") if isinstance(value, dict) else None
            members.append({
                "path": PurePosixPath(relative).as_posix(),
                "media_type": mimetypes.guess_type(relative)[0] or "application/octet-stream",
                "schema_version": schema_version,
                "size_bytes": path.stat().st_size,
                "content_hash": file_hash(path),
            })
        policy_hash = canonical_hash(policy)
        manifest_core = {
            "schema_version": "ds-lite.evidence-manifest.v1",
            "job_id": job_id,
            "work_item_id": work_item_id,
            "policy_id": policy["policy_id"],
            "policy_hash": policy_hash,
            "evidence_class": evidence_class,
            "members": sorted(members, key=lambda item: item["path"]),
        }
        manifest_hash = canonical_hash(manifest_core)
        evidence_set_id = f"evidence-{canonical_hash([job_id, work_item_id, manifest_hash, policy_hash])[:32]}"
        manifest = {**manifest_core, "evidence_set_id": evidence_set_id, "manifest_hash": manifest_hash}
        manifest_path = self.evidence_root / f"{evidence_set_id}.json"
        write_once(manifest_path, manifest)
        self.store.connection.execute("BEGIN IMMEDIATE")
        try:
            self.store._check_fence(work_item_id, owner_id, fence_epoch)
            existing = self.store.connection.execute(
                "SELECT manifest_hash,policy_hash,artifact_root FROM evidence_sets WHERE evidence_set_id=?",
                (evidence_set_id,),
            ).fetchone()
            expected = (manifest_hash, policy_hash, str(artifact_root))
            if existing is not None and tuple(existing) != expected:
                raise IntegrityIncident("evidence set identity conflict")
            self.store.connection.execute(
                "INSERT OR IGNORE INTO evidence_sets(evidence_set_id,job_id,work_item_id,artifact_root,"
                "manifest_path,manifest_hash,policy_id,policy_hash,evidence_class,state,owner_id,fence_epoch,created_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,'frozen',?,?,?)",
                (evidence_set_id, job_id, work_item_id, str(artifact_root), str(manifest_path),
                 manifest_hash, policy["policy_id"], policy_hash, evidence_class,
                 owner_id, fence_epoch, self.store._stamp(self.store._now())),
            )
            for member in manifest["members"]:
                self.store.connection.execute(
                    "INSERT OR IGNORE INTO evidence_members(evidence_set_id,relative_path,media_type,"
                    "schema_version,size_bytes,content_hash) VALUES(?,?,?,?,?,?)",
                    (evidence_set_id, member["path"], member["media_type"], member["schema_version"],
                     member["size_bytes"], member["content_hash"]),
                )
            self.store.connection.commit()
        except Exception:
            self.store.connection.rollback()
            raise
        return manifest

    def store_private_witness(
        self, work_item_id: str, event_class: str, content: bytes, *,
        owner_id: str, fence_epoch: int,
    ) -> dict[str, Any]:
        lowered = content.lower()
        if any(marker in lowered for marker in (b"api_key", b"authorization: bearer", b"password", b"credential")):
            raise EvidenceError("credential-like content is forbidden in private spool")
        content_hash = hashlib.sha256(content).hexdigest()
        witness_id = f"witness-{canonical_hash([work_item_id, event_class, content_hash])[:32]}"
        path = self.private_spool_root / f"{witness_id}.bin"
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            if path.read_bytes() != content:
                raise IntegrityIncident("private witness identity conflict")
        else:
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
        self.store.connection.execute("BEGIN IMMEDIATE")
        try:
            self.store._check_fence(work_item_id, owner_id, fence_epoch)
            self.store.connection.execute(
                "INSERT OR IGNORE INTO private_witness_index(witness_id,work_item_id,event_class,"
                "content_hash,size_bytes,spool_name,redaction_policy,owner_id,fence_epoch,created_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?)",
                (witness_id, work_item_id, event_class, content_hash, len(content), path.name,
                 "ds-lite.redaction.v1", owner_id, fence_epoch, self.store._stamp(self.store._now())),
            )
            self.store.connection.commit()
        except Exception:
            self.store.connection.rollback()
            raise
        return {"witness_id": witness_id, "content_hash": content_hash, "size_bytes": len(content),
                "redaction_policy": "ds-lite.redaction.v1"}


__all__ = ["EvidenceError", "EvidenceManager", "canonical_bytes", "canonical_hash", "file_hash", "write_once"]
