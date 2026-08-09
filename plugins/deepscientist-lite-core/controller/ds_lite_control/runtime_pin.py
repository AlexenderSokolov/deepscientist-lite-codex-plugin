from __future__ import annotations

import hashlib
import json
import os
import subprocess
import re
from pathlib import Path
from typing import Any


_SEMVER_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?$")


def _version_key(value: str) -> tuple[int, int, int, int, str]:
    match = _SEMVER_RE.fullmatch(value)
    if not match:
        raise ValueError(f"invalid Codex version: {value!r}")
    return (
        int(match.group(1)), int(match.group(2)), int(match.group(3)),
        1 if match.group(4) is None else 0, match.group(4) or "",
    )


def schema_manifest_version(schema_root: Path) -> str | None:
    """Read the Codex identity from a schema bundle, never from a code pin."""
    manifest_path = schema_root / "SCHEMA-MANIFEST.json"
    try:
        value = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    version = value.get("codex_version") if isinstance(value, dict) else None
    return version if isinstance(version, str) and _SEMVER_RE.fullmatch(version) else None


def resolve_codex_version(schema_root: Path | None = None, *, explicit: str | None = None) -> str:
    """Resolve runtime identity from explicit input, env override, or schema manifests."""
    if explicit:
        _version_key(explicit)
        return explicit
    env_version = os.environ.get("DS_LITE_CODEX_VERSION", "").strip()
    if env_version:
        _version_key(env_version)
        return env_version
    if schema_root is not None:
        version = schema_manifest_version(schema_root)
        if version:
            return version
    raise ValueError("Codex version is unavailable; pass --codex-version or a schema manifest")


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
    expected_version = resolve_codex_version(schema_root, explicit=expected_version)
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


__all__ = [
    "observe_codex_version", "resolve_codex_version", "schema_manifest_version",
    "verify_runtime_selection", "verify_schema_bundle",
]
