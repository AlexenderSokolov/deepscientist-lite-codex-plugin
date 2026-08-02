#!/usr/bin/env python3
"""Create and validate low-cost, project-local learning receipts."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any


SCHEMA = "ds-lite.learning-receipt.v1"
CATALOG_SCHEMA = "ds-lite.learning-catalog.v1"
PACKAGE = "deepscientist-lite"
PACKAGE_VERSION = "0.8.0-beta.1"
ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
SHA_RE = re.compile(r"^[0-9a-f]{64}$")
SENSITIVE = re.compile(r"(?i)(password|token|secret|api[_-]?key|authorization|cookie|credential)")
MARKER_GROUPS = (("适用", "Applicability"), ("规则", "Rules"), ("易错", "Pitfalls"), ("检查", "Checklist"), ("人工", "Human"))


class LearningError(ValueError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _package_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _catalog_path() -> Path:
    return _package_root() / "references" / "learning" / "tutorial-catalog.json"


def _load_catalog() -> tuple[dict[str, Any], str]:
    path = _catalog_path()
    try:
        raw = path.read_bytes()
        data = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise LearningError(f"learning catalog unavailable: {exc}") from exc
    if not isinstance(data, dict) or data.get("schema_version") != CATALOG_SCHEMA:
        raise LearningError("learning catalog schema is unsupported")
    if data.get("package") != PACKAGE or data.get("package_version") != PACKAGE_VERSION:
        raise LearningError("learning catalog package version is unsupported")
    tutorials = data.get("tutorials")
    if not isinstance(tutorials, list) or not 1 <= len(tutorials) <= 10:
        raise LearningError("tutorial catalog must contain one to ten tutorials")
    seen: set[str] = set()
    for item in tutorials:
        if not isinstance(item, dict) or set(item) != {"id", "version", "path", "sha256"}:
            raise LearningError("tutorial entry fields are invalid")
        ident = item["id"]
        if not isinstance(ident, str) or not ID_RE.fullmatch(ident) or ident in seen:
            raise LearningError("tutorial id is invalid or duplicated")
        seen.add(ident)
        rel = item["path"]
        if not isinstance(rel, str) or PurePosixPath(rel).is_absolute() or PureWindowsPath(rel).is_absolute() or ".." in PurePosixPath(rel).parts:
            raise LearningError(f"tutorial path is not package-relative: {rel}")
        file_path = (_package_root() / rel).resolve()
        try:
            file_path.relative_to(_package_root().resolve())
        except ValueError as exc:
            raise LearningError("tutorial path escapes package") from exc
        if not file_path.is_file():
            raise LearningError(f"tutorial file is missing: {rel}")
        digest = hashlib.sha256(file_path.read_bytes()).hexdigest()
        if item["sha256"] != digest:
            raise LearningError(f"tutorial hash mismatch: {ident}")
    mapping = data.get("skill_map")
    if not isinstance(mapping, dict):
        raise LearningError("skill_map must be an object")
    for skill, ids in mapping.items():
        if not isinstance(skill, str) or not ID_RE.fullmatch(skill) or not isinstance(ids, list) or not 1 <= len(ids) <= 3 or not set(ids).issubset(seen):
            raise LearningError(f"skill_map entry is invalid: {skill}")
    return data, hashlib.sha256(raw).hexdigest()


def _project_rel(root: Path, value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise LearningError("project reference must be non-empty")
    if PurePosixPath(value.replace("\\", "/")).is_absolute() or PureWindowsPath(value).is_absolute():
        raise LearningError("absolute paths are forbidden in learning receipts")
    rel = PurePosixPath(value.replace("\\", "/"))
    if ".." in rel.parts or not rel.parts:
        raise LearningError("learning reference must remain project-relative")
    candidate = (root / Path(*rel.parts)).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError as exc:
        raise LearningError("learning reference escapes project") from exc
    return rel.as_posix()


def _paths(root: Path, skill: str) -> tuple[Path, Path]:
    if not ID_RE.fullmatch(skill):
        raise LearningError("skill id is invalid")
    return root / "research" / "learning" / f"{skill}.json", root / "research" / "artifacts" / "learning" / f"{skill}.md"


def _tutorial_refs(catalog: dict[str, Any], skill: str) -> list[dict[str, str]]:
    ids = catalog.get("skill_map", {}).get(skill)
    if not isinstance(ids, list) or not ids:
        raise LearningError(f"skill is not registered in learning catalog: {skill}")
    entries = {item["id"]: item for item in catalog["tutorials"]}
    return [{"id": ident, "version": entries[ident]["version"], "sha256": entries[ident]["sha256"]} for ident in ids]


def _validate_summary(summary: str) -> None:
    if not summary.strip() or len(summary) > 2000:
        raise LearningError("learning summary must contain one to two thousand characters")
    if SENSITIVE.search(summary):
        raise LearningError("learning summary contains a sensitive marker")
    missing = ["/".join(group) for group in MARKER_GROUPS if not any(marker in summary for marker in group)]
    if missing:
        raise LearningError("learning summary missing labels: " + ", ".join(missing))


def _receipt(root: Path, skill: str, summary: str, catalog: dict[str, Any], catalog_hash: str, summary_ref: str, reason: str) -> dict[str, Any]:
    stored_summary = summary.rstrip() + "\n"
    summary_hash = hashlib.sha256(stored_summary.encode("utf-8")).hexdigest()
    return {
        "schema_version": SCHEMA,
        "receipt_id": f"learning-{skill}-{uuid.uuid4().hex[:12]}",
        "package": PACKAGE,
        "package_version": PACKAGE_VERSION,
        "skill": skill,
        "catalog_sha256": catalog_hash,
        "tutorial_refs": _tutorial_refs(catalog, skill),
        "summary_ref": summary_ref,
        "summary_sha256": summary_hash,
        "learned_at": _now(),
        "refresh_reason": reason or "first-learning",
        "status": "current",
        "extensions": {},
    }


def validate_receipt(root: Path, payload: Any) -> dict[str, Any]:
    required = {"schema_version", "receipt_id", "package", "package_version", "skill", "catalog_sha256", "tutorial_refs", "summary_ref", "summary_sha256", "learned_at", "refresh_reason", "status", "extensions"}
    if not isinstance(payload, dict) or set(payload) != required:
        raise LearningError("learning receipt fields do not match ds-lite.learning-receipt.v1")
    if payload["schema_version"] != SCHEMA or payload["package"] != PACKAGE or payload["package_version"] != PACKAGE_VERSION:
        raise LearningError("learning receipt is stale")
    if not isinstance(payload["skill"], str) or not ID_RE.fullmatch(payload["skill"]):
        raise LearningError("learning receipt skill is invalid")
    if not SHA_RE.fullmatch(str(payload["catalog_sha256"])) or not SHA_RE.fullmatch(str(payload["summary_sha256"])):
        raise LearningError("learning receipt hash is invalid")
    if payload["status"] != "current" or not isinstance(payload["extensions"], dict):
        raise LearningError("learning receipt is not current")
    summary_ref = _project_rel(root, payload["summary_ref"])
    summary_path = root / Path(*PurePosixPath(summary_ref).parts)
    if not summary_path.is_file():
        raise LearningError("learning summary is missing")
    summary = summary_path.read_text(encoding="utf-8")
    _validate_summary(summary)
    if hashlib.sha256(summary.encode("utf-8")).hexdigest() != payload["summary_sha256"]:
        raise LearningError("learning summary hash does not match receipt")
    return json.loads(json.dumps(payload))


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(content, encoding="utf-8")
    os.replace(temporary, path)


def learn(root: Path, skill: str, summary: str, reason: str = "") -> dict[str, Any]:
    root = root.expanduser().resolve()
    if not root.is_dir():
        raise LearningError("project root must be an existing directory")
    _validate_summary(summary)
    catalog, catalog_hash = _load_catalog()
    receipt_path, summary_path = _paths(root, skill)
    summary_ref = summary_path.relative_to(root).as_posix()
    if receipt_path.exists():
        try:
            current = validate_receipt(root, json.loads(receipt_path.read_text(encoding="utf-8")))
            if current["catalog_sha256"] == catalog_hash and current["tutorial_refs"] == _tutorial_refs(catalog, skill):
                return {"schema_version": SCHEMA, "status": "current", "reused": True, "receipt_ref": receipt_path.relative_to(root).as_posix(), "summary_ref": summary_ref}
        except (OSError, UnicodeError, json.JSONDecodeError, LearningError):
            pass
    payload = _receipt(root, skill, summary, catalog, catalog_hash, summary_ref, reason)
    _write(summary_path, summary.rstrip() + "\n")
    _write(receipt_path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    return {"schema_version": SCHEMA, "status": "current", "reused": False, "receipt_ref": receipt_path.relative_to(root).as_posix(), "summary_ref": summary_ref}


def ensure(root: Path, skill: str) -> dict[str, Any]:
    root = root.expanduser().resolve()
    receipt_path, _ = _paths(root, skill)
    if not receipt_path.is_file():
        raise LearningError("learning receipt is missing")
    catalog, catalog_hash = _load_catalog()
    payload = validate_receipt(root, json.loads(receipt_path.read_text(encoding="utf-8")))
    if payload["catalog_sha256"] != catalog_hash or payload["tutorial_refs"] != _tutorial_refs(catalog, skill):
        raise LearningError("learning receipt is stale")
    return {"schema_version": SCHEMA, "status": "current", "reused": True, "receipt_ref": receipt_path.relative_to(root).as_posix(), "summary_ref": payload["summary_ref"]}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate or create DS Lite learning receipts.")
    sub = parser.add_subparsers(dest="command", required=True)
    catalog_cmd = sub.add_parser("catalog")
    catalog_cmd.add_argument("--path", action="store_true")
    for name in ("learn", "ensure"):
        cmd = sub.add_parser(name)
        cmd.add_argument("--root", required=True)
        cmd.add_argument("--skill", required=True)
        if name == "learn":
            cmd.add_argument("--summary", required=True)
            cmd.add_argument("--refresh-reason", default="")
    args = parser.parse_args(argv)
    try:
        if args.command == "catalog":
            catalog, digest = _load_catalog()
            print(json.dumps({**catalog, "catalog_sha256": digest}, ensure_ascii=True))
        elif args.command == "learn":
            print(json.dumps(learn(Path(args.root), args.skill, args.summary, args.refresh_reason), ensure_ascii=True))
        else:
            print(json.dumps(ensure(Path(args.root), args.skill), ensure_ascii=True))
    except (OSError, UnicodeError, json.JSONDecodeError, LearningError) as exc:
        print(json.dumps({"schema_version": SCHEMA, "status": "blocked", "error": str(exc)}, ensure_ascii=True))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
