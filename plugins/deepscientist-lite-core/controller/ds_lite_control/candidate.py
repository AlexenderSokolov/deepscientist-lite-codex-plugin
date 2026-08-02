from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path
from typing import Any, Iterable


EXCLUDED_DIR_NAMES = {
    ".git", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    "System.Management.Automation.Internal.Host.InternalHost",
}
EXCLUDED_DIR_PREFIXES = (".tmp-", "ds-lite-autoresearch-runner-")


def _canonical_digest(value: Any) -> str:
    encoded = json.dumps(
        value, ensure_ascii=True, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _excluded(relative: Path) -> bool:
    parts = relative.parts
    return (
        any(part in EXCLUDED_DIR_NAMES for part in parts)
        or any(part.startswith(EXCLUDED_DIR_PREFIXES) for part in parts)
        or (bool(parts) and parts[0] == "research")
        or any(part.startswith(".validation-tmp") for part in parts)
    )


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_candidate_manifest(root: Path) -> dict[str, Any]:
    source_root = root.resolve()
    files: list[dict[str, Any]] = []
    for current, directories, names in os.walk(source_root, topdown=True):
        current_path = Path(current)
        directories[:] = sorted(
            name for name in directories
            if not _excluded((current_path / name).relative_to(source_root))
        )
        for name in sorted(names):
            path = current_path / name
            relative = path.relative_to(source_root)
            if _excluded(relative):
                continue
            if path.is_symlink() or not path.is_file():
                raise ValueError(f"candidate contains unsupported file: {relative.as_posix()}")
            files.append({
                "path": relative.as_posix(),
                "sha256": _file_digest(path),
                "size": path.stat().st_size,
            })
    manifest = {
        "schema_version": "ds-lite.candidate-manifest.v1",
        "files": files,
    }
    manifest["candidate_digest"] = _canonical_digest(manifest)
    return manifest


def build_repository_candidate_manifest(root: Path) -> dict[str, Any]:
    source_root = root.resolve()
    completed = subprocess.run(
        ["git", "-C", str(source_root), "ls-files", "-z", "--cached", "--others",
         "--exclude-standard"],
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError("git candidate enumeration failed")
    names = completed.stdout.decode("utf-8", errors="surrogateescape").split("\0")
    files: list[dict[str, Any]] = []
    for name in sorted(value for value in names if value):
        relative = Path(name)
        if _excluded(relative):
            continue
        path = (source_root / relative).resolve()
        try:
            path.relative_to(source_root)
        except ValueError as exc:
            raise ValueError("candidate path escapes repository") from exc
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"candidate contains unsupported file: {relative.as_posix()}")
        files.append({
            "path": relative.as_posix(),
            "sha256": _file_digest(path),
            "size": path.stat().st_size,
        })
    manifest = {
        "schema_version": "ds-lite.candidate-manifest.v1",
        "files": files,
    }
    manifest["candidate_digest"] = _canonical_digest(manifest)
    return manifest


def write_candidate_manifest(output: Path, manifest: dict[str, Any]) -> None:
    if manifest.get("schema_version") != "ds-lite.candidate-manifest.v1":
        raise ValueError("unsupported candidate manifest")
    path = output.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(
        manifest, ensure_ascii=True, sort_keys=True, separators=(",", ":")
    ) + "\n"
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())


def bind_release_candidate(
    source_manifest: dict[str, Any],
    package_manifests: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    source_digest = source_manifest.get("candidate_digest")
    if not isinstance(source_digest, str) or len(source_digest) != 64:
        raise ValueError("source candidate digest is required")
    packages: dict[str, str] = {}
    for platform_name, manifest in sorted(package_manifests.items()):
        digest = manifest.get("candidate_digest")
        if not isinstance(platform_name, str) or not platform_name:
            raise ValueError("package platform is required")
        if not isinstance(digest, str) or len(digest) != 64:
            raise ValueError("package candidate digest is required")
        packages[platform_name] = digest
    binding = {
        "schema_version": "ds-lite.release-candidate.v1",
        "source_digest": source_digest,
        "package_digests": packages,
    }
    binding["candidate_digest"] = _canonical_digest(binding)
    return binding


def aggregate_candidate_bound_gates(
    candidate_digest: str,
    required_gates: Iterable[str],
    gate_receipts: Iterable[dict[str, Any]],
) -> dict[str, Any]:
    required = list(required_gates)
    rows: dict[str, dict[str, Any]] = {}
    duplicate_gates: list[str] = []
    for receipt in gate_receipts:
        gate_id = receipt.get("gate_id")
        if not isinstance(gate_id, str) or not gate_id:
            continue
        if gate_id in rows:
            duplicate_gates.append(gate_id)
        else:
            rows[gate_id] = receipt
    missing = [gate for gate in required if gate not in rows]
    nonpassing = [
        gate for gate in required
        if gate in rows and rows[gate].get("status") != "passed"
    ]
    mismatched = [
        gate for gate in required
        if gate in rows and rows[gate].get("candidate_digest") != candidate_digest
    ]
    duplicates = sorted(set(gate for gate in duplicate_gates if gate in required))
    allowed = not missing and not nonpassing and not mismatched and not duplicates
    return {
        "schema_version": "ds-lite.candidate-bound-aggregate.v1",
        "candidate_digest": candidate_digest,
        "required_gates": required,
        "missing_gates": missing,
        "nonpassing_gates": nonpassing,
        "candidate_mismatch_gates": mismatched,
        "duplicate_gates": duplicates,
        "status": "allowed" if allowed else "blocked",
        "release_allowed": allowed,
    }


__all__ = [
    "aggregate_candidate_bound_gates", "bind_release_candidate",
    "build_candidate_manifest", "build_repository_candidate_manifest",
    "write_candidate_manifest",
]
