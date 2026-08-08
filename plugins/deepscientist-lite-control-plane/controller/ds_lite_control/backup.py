from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
from pathlib import Path
from typing import Any


def _hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _backup_database(source: Path, destination: Path) -> None:
    source_connection = sqlite3.connect(f"file:{source.resolve().as_posix()}?mode=ro", uri=True)
    destination_connection = sqlite3.connect(destination)
    try:
        source_connection.backup(destination_connection)
    finally:
        destination_connection.close()
        source_connection.close()


def backup_control_plane(source: Path, destination: Path, *, require_protocol: bool = False,
                         require_broker: bool = False,
                         require_supervisor: bool = False,
                         require_evidence: bool = False) -> dict[str, Any]:
    source = source.resolve()
    destination = destination.resolve()
    required = [source / "control.sqlite3", source / "runtime.sqlite3", source / "receipts"]
    protocol = source / "protocol-journal.jsonl"
    broker_metadata = source / "broker-metadata.json"
    supervisor_state = source / "supervisor" / "supervisor-state.json"
    evidence_root = source / "evidence"
    private_spool = source / "private-spool"
    if (not all(path.exists() for path in required)
            or (require_protocol and not protocol.is_file())
            or (require_broker and (not protocol.is_file() or not broker_metadata.is_file()))
            or (require_supervisor and not supervisor_state.is_file())
            or (require_evidence and (
                not evidence_root.is_dir() or not private_spool.is_dir()
                or not any(evidence_root.iterdir()) or not any(private_spool.iterdir())
            ))):
        raise FileNotFoundError("control.sqlite3, runtime.sqlite3, and receipts are all required")
    destination.mkdir(parents=True, exist_ok=False)
    _backup_database(required[0], destination / "control.sqlite3")
    _backup_database(required[1], destination / "runtime.sqlite3")
    receipts = destination / "receipts"
    receipts.mkdir()
    for source_receipt in sorted(required[2].glob("*.json")):
        shutil.copy2(source_receipt, receipts / source_receipt.name)
    files = [destination / "control.sqlite3", destination / "runtime.sqlite3", *sorted(receipts.glob("*.json"))]
    if protocol.is_file():
        shutil.copy2(protocol, destination / protocol.name)
        files.append(destination / protocol.name)
    if broker_metadata.is_file():
        shutil.copy2(broker_metadata, destination / broker_metadata.name)
        files.append(destination / broker_metadata.name)
    if supervisor_state.is_file():
        supervisor_destination = destination / "supervisor"
        supervisor_destination.mkdir()
        shutil.copy2(supervisor_state, supervisor_destination / supervisor_state.name)
        files.append(supervisor_destination / supervisor_state.name)
    if evidence_root.is_dir() and private_spool.is_dir():
        for source_root, name in ((evidence_root, "evidence"), (private_spool, "private-spool")):
            target_root = destination / name
            target_root.mkdir()
            for item in sorted(path for path in source_root.rglob("*") if path.is_file()):
                relative = item.relative_to(source_root)
                target = target_root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(item, target)
                files.append(target)
    broker = None
    if broker_metadata.is_file() and protocol.is_file():
        metadata = json.loads(broker_metadata.read_text(encoding="utf-8"))
        lines = [line for line in protocol.read_text(encoding="utf-8").splitlines() if line]
        last_sequence = int(json.loads(lines[-1]).get("sequence", 0)) if lines else 0
        broker = {
            "broker_id_sha256": hashlib.sha256(str(metadata.get("broker_id", "")).encode()).hexdigest(),
            "last_sequence": last_sequence,
            "journal_sha256": _hash(protocol),
        }
    manifest = {
        "schema_version": ("ds-lite.control-backup.v5" if evidence_root.is_dir() and private_spool.is_dir() else
                           "ds-lite.control-backup.v4" if supervisor_state.is_file() else
                           "ds-lite.control-backup.v3" if broker is not None else
                           "ds-lite.control-backup.v2" if protocol.is_file() else "ds-lite.control-backup.v1"),
        "complete": True,
        "files": {path.relative_to(destination).as_posix(): _hash(path) for path in files},
    }
    if broker is not None:
        manifest["broker"] = broker
    if supervisor_state.is_file():
        manifest["supervisor"] = {
            "status_sha256": _hash(supervisor_state),
            "installed_as_system_service": False,
        }
    if manifest["schema_version"] == "ds-lite.control-backup.v5":
        manifest["evidence"] = {
            "manifest_count": len(list((destination / "evidence").rglob("*.*"))),
            "private_witness_count": len(list((destination / "private-spool").rglob("*.*"))),
            "private_spool_os_confidentiality": "not-claimed",
        }
    with (destination / "manifest.json").open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(manifest, handle, ensure_ascii=True, indent=2, sort_keys=True)
        handle.write("\n")
    return manifest


def verify_backup(root: Path) -> dict[str, Any]:
    root = root.resolve()
    try:
        manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
        valid = bool(manifest.get("complete")) and all(
            (root / relative).is_file() and _hash(root / relative) == expected
            for relative, expected in manifest.get("files", {}).items()
        )
        required = {"control.sqlite3", "runtime.sqlite3"}
        valid = valid and required.issubset(manifest.get("files", {}))
        if manifest.get("schema_version") == "ds-lite.control-backup.v3":
            broker = manifest.get("broker")
            valid = bool(valid and isinstance(broker, dict)
                         and "protocol-journal.jsonl" in manifest.get("files", {})
                         and "broker-metadata.json" in manifest.get("files", {})
                         and broker.get("journal_sha256") == manifest["files"]["protocol-journal.jsonl"])
        if manifest.get("schema_version") in {"ds-lite.control-backup.v4", "ds-lite.control-backup.v5"}:
            supervisor = manifest.get("supervisor")
            valid = bool(
                valid and isinstance(supervisor, dict)
                and "supervisor/supervisor-state.json" in manifest.get("files", {})
                and supervisor.get("status_sha256")
                == manifest["files"]["supervisor/supervisor-state.json"]
                and supervisor.get("installed_as_system_service") is False
            )
        if manifest.get("schema_version") == "ds-lite.control-backup.v5":
            evidence = manifest.get("evidence")
            files = manifest.get("files", {})
            valid = bool(
                valid and isinstance(evidence, dict)
                and any(name.startswith("evidence/") for name in files)
                and any(name.startswith("private-spool/") for name in files)
                and evidence.get("private_spool_os_confidentiality") == "not-claimed"
            )
        return {"valid": bool(valid), "manifest": manifest}
    except (OSError, ValueError, json.JSONDecodeError):
        return {"valid": False, "manifest": None}


def restore_control_plane(backup: Path, destination: Path) -> dict[str, Any]:
    backup = backup.resolve()
    destination = destination.resolve()
    if destination.exists():
        raise FileExistsError(destination)
    verification = verify_backup(backup)
    if not verification["valid"]:
        raise ValueError("backup manifest is incomplete or invalid")
    destination.mkdir(parents=True, exist_ok=False)
    shutil.copy2(backup / "control.sqlite3", destination / "control.sqlite3")
    shutil.copy2(backup / "runtime.sqlite3", destination / "runtime.sqlite3")
    (destination / "receipts").mkdir()
    for receipt in sorted((backup / "receipts").glob("*.json")):
        shutil.copy2(receipt, destination / "receipts" / receipt.name)
    if (backup / "protocol-journal.jsonl").is_file():
        shutil.copy2(backup / "protocol-journal.jsonl", destination / "protocol-journal.jsonl")
    if (backup / "broker-metadata.json").is_file():
        shutil.copy2(backup / "broker-metadata.json", destination / "broker-metadata.json")
    if (backup / "supervisor" / "supervisor-state.json").is_file():
        (destination / "supervisor").mkdir()
        shutil.copy2(
            backup / "supervisor" / "supervisor-state.json",
            destination / "supervisor" / "supervisor-state.json",
        )
    for name in ("evidence", "private-spool"):
        source_root = backup / name
        if source_root.is_dir():
            target_root = destination / name
            target_root.mkdir()
            for item in sorted(path for path in source_root.rglob("*") if path.is_file()):
                relative = item.relative_to(source_root)
                target = target_root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(item, target)
    control = sqlite3.connect(f"file:{(destination / 'control.sqlite3').as_posix()}?mode=ro", uri=True)
    runtime = sqlite3.connect(f"file:{(destination / 'runtime.sqlite3').as_posix()}?mode=ro", uri=True)
    try:
        control_ok = control.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        runtime_ok = runtime.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        runtime.close()
        control.close()
    return {"valid": bool(control_ok and runtime_ok), "destination": str(destination)}
