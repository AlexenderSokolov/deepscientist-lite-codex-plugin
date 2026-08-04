#!/usr/bin/env python3
"""Validate a fresh local Codex marketplace cache without a model request."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


STABLE_CODEX_VERSION = "0.146.0"
ROOT = Path(__file__).resolve().parents[1]
CONTROLLER_ROOT = ROOT / "plugins" / "deepscientist-lite-core" / "controller"
if str(CONTROLLER_ROOT) not in sys.path:
    sys.path.insert(0, str(CONTROLLER_ROOT))

from ds_lite_control.runtime_pin import verify_runtime_selection  # noqa: E402


EXPECTED_PACKAGES = {
    "deepscientist-lite": "0.9.0-beta.1",
    "deepscientist-lite-academic": "0.9.0-beta.1",
    "deepscientist-lite-web": "0.3.0-alpha.1",
    "deepscientist-lite-knowledge": "0.3.0-alpha.1",
    "deepscientist-lite-empirical": "0.3.0-alpha.1",
    "deepscientist-lite-engineering": "0.3.0-alpha.1",
}


class FormalCacheError(RuntimeError):
    pass


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def _valid_digest(value: Any) -> bool:
    return (
        isinstance(value, str) and len(value) == 64
        and all(character in "0123456789abcdef" for character in value.lower())
    )


def _run(command: list[str], env: dict[str, str], cwd: Path) -> tuple[int | None, int, str, Any]:
    try:
        result = subprocess.run(command, cwd=str(cwd), env=env, text=True, encoding="utf-8", errors="replace",
                                capture_output=True, check=False)
    except OSError:
        return None, 0, hashlib.sha256(b"spawn-error").hexdigest(), None
    raw = result.stdout + result.stderr
    try:
        parsed = json.loads(result.stdout)
    except json.JSONDecodeError:
        parsed = None
    return result.returncode, len([line for line in raw.splitlines() if line]), hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest(), parsed


def _observed_packages(value: Any) -> dict[str, str]:
    observed: dict[str, str] = {}
    if isinstance(value, dict):
        name = value.get("name")
        version = value.get("version")
        if isinstance(name, str) and isinstance(version, str) and name in EXPECTED_PACKAGES:
            observed[name] = version
        for child in value.values():
            observed.update(_observed_packages(child))
    elif isinstance(value, list):
        for child in value:
            observed.update(_observed_packages(child))
    return observed


def validate_receipt(value: dict[str, Any]) -> dict[str, Any]:
    """Normalize current and historical v1 receipts without upgrading evidence."""
    if not isinstance(value, dict) or value.get("schema_version") != "ds-lite.formal-cache-acceptance.v1":
        raise FormalCacheError("unsupported formal cache receipt schema")
    identity = value.get("cli_identity")
    if not isinstance(identity, dict):
        raise FormalCacheError("formal cache receipt has no CLI identity")
    if isinstance(identity.get("observed_version"), str):
        observed_version = identity["observed_version"]
        generation = "stable-runtime-verified"
    elif isinstance(identity.get("version"), str):
        observed_version = identity["version"]
        generation = "legacy"
    else:
        raise FormalCacheError("formal cache receipt CLI version is invalid")
    if value.get("status") not in {"passed", "blocked"}:
        raise FormalCacheError("formal cache receipt status is invalid")
    if value.get("model_request_made") is not False:
        raise FormalCacheError("formal cache receipt crossed the model boundary")
    return {
        "schema_version": value["schema_version"],
        "status": value["status"],
        "observed_version": observed_version,
        "receipt_generation": generation,
    }


def run(
    *, codex_bin: Path | str, repo_root: Path | str, output_root: Path | str,
    schema_root: Path | str, expected_version: str, expected_sha256: str,
    candidate_digest: str,
) -> dict[str, Any]:
    binary = Path(codex_bin)
    repo = Path(repo_root)
    root = Path(output_root)
    if root.exists():
        raise FormalCacheError("formal cache identity already exists; refusing overwrite")
    if expected_version != STABLE_CODEX_VERSION:
        raise FormalCacheError("formal cache acceptance requires stable 0.146.0")
    if not _valid_digest(candidate_digest):
        raise FormalCacheError("candidate digest must be a SHA-256 value")
    if (
        not binary.is_file() or not repo.is_dir()
        or not isinstance(expected_sha256, str)
        or _sha256(binary) != expected_sha256.upper()
    ):
        raise FormalCacheError("selected binary, SHA-256, or repository is unavailable")
    try:
        runtime = verify_runtime_selection(
            binary, Path(schema_root), expected_version=expected_version,
        )
    except (OSError, RuntimeError, UnicodeError, ValueError) as exc:
        raise FormalCacheError("selected runtime or schema bundle is invalid") from exc
    if not runtime.get("valid") or not runtime.get("schema", {}).get("valid"):
        raise FormalCacheError("selected runtime or schema bundle is invalid")
    root.mkdir(parents=True)
    home = root / "codex-home"
    home.mkdir()
    env = os.environ.copy()
    env["CODEX_HOME"] = str(home)
    commands = [("marketplace", [str(binary), "plugin", "marketplace", "add", str(repo)])]
    commands.extend((name, [str(binary), "plugin", "add", f"{name}@deepscientist-lite"]) for name in EXPECTED_PACKAGES)
    observations: list[dict[str, object]] = []
    for label, command in commands:
        returncode, line_count, digest, _ = _run(command, env, repo)
        observations.append({"label": label, "returncode_observed": returncode is not None, "returncode": returncode,
                             "output_line_count": line_count, "output_sha256": digest})
        if returncode != 0:
            break
    list_returncode, list_lines, list_digest, listed = _run([str(binary), "plugin", "list", "--json"], env, repo)
    observations.append({"label": "plugin-list", "returncode_observed": list_returncode is not None, "returncode": list_returncode,
                         "output_line_count": list_lines, "output_sha256": list_digest})
    observed = _observed_packages(listed)
    expected = EXPECTED_PACKAGES
    passed = all(item["returncode"] == 0 for item in observations) and observed == expected
    receipt = {
        "schema_version": "ds-lite.formal-cache-acceptance.v1",
        "status": "passed" if passed else "blocked",
        "failure_layer": "none" if passed else "formal-cache",
        "candidate_digest": candidate_digest,
        "cli_identity": {
            "expected_version": expected_version,
            "observed_version": runtime["codex_binary_version"],
            "sha256": _sha256(binary).lower(),
            "sha256_match": True,
        },
        "schema_identity": {
            "valid": runtime["schema"]["valid"],
            "manifest_sha256": runtime["schema"]["manifest_digest"],
            "bundle_sha256": runtime["schema"]["observed_bundle_digest"],
        },
        "marketplace_source": "local",
        "expected_packages": expected,
        "observed_packages": observed,
        "command_observations": observations,
        "model_request_made": False,
        "raw_output_persisted": False,
        "raw_error_text_persisted": False,
    }
    path = root / "formal-cache-acceptance.json"
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(receipt, handle, ensure_ascii=True, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description="Create and inspect one fresh local formal cache identity.")
    parser.add_argument("--codex-bin", required=True)
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--schema-root", required=True)
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--candidate-digest", required=True)
    args = parser.parse_args()
    try:
        receipt = run(
            codex_bin=args.codex_bin, repo_root=args.repo_root,
            output_root=args.output_root, schema_root=args.schema_root,
            expected_version=args.expected_version, expected_sha256=args.expected_sha256,
            candidate_digest=args.candidate_digest,
        )
    except FormalCacheError as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc)}))
        return 2
    print(json.dumps({"status": receipt["status"], "failure_layer": receipt["failure_layer"]}))
    return 0 if receipt["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
