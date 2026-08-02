#!/usr/bin/env python3
"""Acquire and verify the immutable Codex executable used by real acceptance."""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import subprocess
import sys
import tarfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

EXPECTED_VERSION = "0.144.5"
EXPECTED_BINARY_SHA256 = "EFDB3540EF74B9909408C8D38DA79483454797B36F471E3E004FC2BF2B70E22A"
EXPECTED_PACKAGES = {
    "@openai/codex@0.144.5": "jjB+K+OMv572mKhS+2QuLxWXDJNdpwbPenf+V+8bdq7wg4Scqt3cn6WEekD8wPqDVZqck0HSX17K9rD9kbDJQA==",
    "@openai/codex@0.144.5-win32-x64": "DnsSTlnnzleTxvLwIGnBitKInscxn2I7qASqosS8Fv+qysBygd+ZiBn/SQsRCgQ28PAlsNzmd3Gf3ZTecolAmg==",
}
PROJECT_TEMP_ROOT = (Path(__file__).resolve().parents[2] / "research" / ".validation-tmp").resolve()


class PinError(RuntimeError):
    pass


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def _sha512_integrity(path: Path) -> str:
    digest = hashlib.sha512(path.read_bytes()).digest()
    return base64.b64encode(digest).decode("ascii")


def _npm_pack(spec: str, root: Path) -> tuple[Path, str]:
    npm = "npm.cmd" if os.name == "nt" else "npm"
    result = subprocess.run(
        [npm, "pack", spec, "--pack-destination", str(root), "--json"],
        cwd=str(root), capture_output=True, text=True, encoding="utf-8", errors="replace", check=False,
    )
    if result.returncode != 0:
        raise PinError(f"npm pack failed for {spec}")
    try:
        payload = json.loads(result.stdout)
        filename = str(payload[0]["filename"])
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise PinError(f"npm pack returned malformed metadata for {spec}") from exc
    tarball = (root / filename).resolve()
    if not tarball.is_file():
        raise PinError(f"npm pack output is missing for {spec}")
    observed = _sha512_integrity(tarball)
    expected = EXPECTED_PACKAGES.get(spec)
    if expected and observed != expected:
        raise PinError(f"npm integrity mismatch for {spec}")
    return tarball, observed


def _extract(tarball: Path, destination: Path) -> None:
    with tarfile.open(tarball, "r:gz") as archive:
        for member in archive.getmembers():
            target = (destination / member.name).resolve()
            if destination.resolve() not in target.parents:
                raise PinError("tarball contains an unsafe path")
        archive.extractall(destination)


def acquire(output_root: Path) -> dict[str, Any]:
    try:
        output_root.resolve().relative_to(PROJECT_TEMP_ROOT)
    except ValueError as exc:
        raise PinError("output root must be below research/.validation-tmp") from exc
    if output_root.exists():
        raise PinError("output root already exists; refusing overwrite")
    output_root.mkdir(parents=True)
    packages = output_root / "packages"
    packages.mkdir()
    tarballs: list[dict[str, str]] = []
    extracted = output_root / "extracted"
    extracted.mkdir()
    for spec in EXPECTED_PACKAGES:
        tarball, integrity = _npm_pack(spec, packages)
        target = extracted / ("meta" if "-win32-x64" not in spec else "platform")
        target.mkdir()
        _extract(tarball, target)
        tarballs.append({"spec": spec, "filename": tarball.name, "sha512_base64": integrity})
    candidates = sorted(extracted.glob("**/codex.exe"))
    if len(candidates) != 1:
        raise PinError(f"expected one codex.exe, found {len(candidates)}")
    codex = candidates[0]
    observed_sha = _sha256(codex)
    status = "passed" if observed_sha == EXPECTED_BINARY_SHA256 else "blocked"
    receipt: dict[str, Any] = {
        "schema_version": "ds-lite.codex-pin.v1",
        "status": status,
        "version": EXPECTED_VERSION,
        "expected_sha256": EXPECTED_BINARY_SHA256,
        "observed_sha256": observed_sha,
        "codex_bin_ref": codex.relative_to(output_root).as_posix() if status == "passed" else "",
        "tarballs": tarballs,
        "retrieved_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "raw_output_persisted": False,
        "extensions": {"failure_layer": "none" if status == "passed" else "pin-drift"},
    }
    (output_root / "codex-pin.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8", newline="\n")
    if status != "passed":
        raise PinError("Codex binary SHA-256 does not match the frozen pin")
    return receipt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    default_root = PROJECT_TEMP_ROOT / f"codex-pin-{os.getpid()}"
    parser.add_argument("--output-root", default=os.environ.get("TEMP_ROOT", str(default_root)))
    args = parser.parse_args(argv)
    if not args.output_root:
        print(json.dumps({"status": "not-observed", "failure_layer": "environment-write", "next_action": "set-authorized-temp-root"}))
        return 2
    try:
        receipt = acquire(Path(args.output_root).expanduser().resolve())
    except (OSError, PinError) as exc:
        print(json.dumps({"status": "blocked", "failure_layer": "acquisition", "reason": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps({"status": receipt["status"], "codex_bin_ref": receipt["codex_bin_ref"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
