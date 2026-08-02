from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_digest(value: Any) -> str:
    encoded = json.dumps(
        value, ensure_ascii=True, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def verify_schema_bundle(
    schema_root: Path, *, expected_version: str, expected_platform: str | None = None
) -> dict[str, Any]:
    root = schema_root.resolve()
    manifest_path = root / "SCHEMA-MANIFEST.json"
    try:
        manifest_bytes = manifest_path.read_bytes()
        manifest = json.loads(manifest_bytes.decode("utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {
            "valid": False,
            "codex_version": None,
            "platform": None,
            "manifest_digest": "missing",
            "expected_bundle_digest": "missing",
            "observed_bundle_digest": "missing",
            "missing_files": ["SCHEMA-MANIFEST.json"],
            "drifted_files": [],
        }
    files = manifest.get("files")
    if (
        manifest.get("schema_version") != "ds-lite.codex-schema-pin.v1"
        or not isinstance(files, dict)
        or not files
    ):
        raise ValueError("unsupported or empty Codex schema manifest")
    missing: list[str] = []
    drifted: list[str] = []
    observed: dict[str, str] = {}
    for name, expected_digest in sorted(files.items()):
        if not isinstance(name, str) or not isinstance(expected_digest, str):
            raise ValueError("invalid Codex schema manifest entry")
        relative = Path(name)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("Codex schema manifest path escapes schema root")
        path = (root / relative).resolve()
        try:
            path.relative_to(root)
        except ValueError as exc:
            raise ValueError("Codex schema manifest path escapes schema root") from exc
        if not path.is_file():
            missing.append(name)
            continue
        actual_digest = _sha256(path)
        observed[name] = actual_digest
        if actual_digest != expected_digest:
            drifted.append(name)
    version = manifest.get("codex_version")
    observed_platform = manifest.get("platform")
    expected_bundle_digest = _canonical_digest(files)
    observed_bundle_digest = _canonical_digest(observed)
    return {
        "valid": (
            version == expected_version
            and (expected_platform is None or observed_platform == expected_platform)
            and not missing
            and not drifted
            and len(observed) == len(files)
        ),
        "codex_version": version,
        "platform": observed_platform,
        "manifest_digest": hashlib.sha256(manifest_bytes).hexdigest(),
        "expected_bundle_digest": expected_bundle_digest,
        "observed_bundle_digest": observed_bundle_digest,
        "missing_files": missing,
        "drifted_files": drifted,
    }


def observe_codex_version(codex_bin: Path, *, timeout: float = 15.0) -> str:
    completed = subprocess.run(
        [str(codex_bin.resolve()), "--version"],
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError("selected Codex binary did not report a version")
    prefix = "codex-cli "
    output = completed.stdout.strip()
    if not output.startswith(prefix) or not output[len(prefix):]:
        raise ValueError("unexpected Codex version output")
    return output[len(prefix):]


def verify_runtime_selection(
    codex_bin: Path, schema_root: Path, *, expected_version: str,
    expected_platform: str | None = None,
) -> dict[str, Any]:
    observed_version = observe_codex_version(codex_bin)
    schema = verify_schema_bundle(
        schema_root, expected_version=expected_version,
        expected_platform=expected_platform,
    )
    return {
        "valid": observed_version == expected_version and schema["valid"],
        "expected_codex_version": expected_version,
        "codex_binary_version": observed_version,
        "expected_platform": expected_platform,
        "schema": schema,
    }


__all__ = ["observe_codex_version", "verify_runtime_selection", "verify_schema_bundle"]
