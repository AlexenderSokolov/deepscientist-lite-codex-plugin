"""Install a pinned dependency lock while handling platform-specific wheel hashes."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path


_PIN_RE = re.compile(r"^([A-Za-z0-9_.-]+)==([^\s]+)")


def read_pins(lock: Path) -> list[tuple[str, str]]:
    pins: list[tuple[str, str]] = []
    for raw in lock.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        match = _PIN_RE.match(line)
        if not match:
            raise ValueError(f"unsupported lock line: {line}")
        pins.append((match.group(1), match.group(2)))
    if not pins:
        raise ValueError("dependency lock is empty")
    return pins


def install(lock: Path) -> dict[str, object]:
    pins = read_pins(lock.resolve())
    # Hashes in the repository lock are artifact-specific. CI resolves the
    # exact pinned versions for its host, then verifies those versions below.
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".txt", delete=False) as handle:
        requirements = Path(handle.name)
        for name, version in pins:
            handle.write(f"{name}=={version}\n")
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "--disable-pip-version-check", "-r", str(requirements)],
            check=True,
        )
        subprocess.run([sys.executable, "-m", "pip", "check"], check=True)
    finally:
        requirements.unlink(missing_ok=True)

    installed: dict[str, str] = {}
    for name, expected in pins:
        try:
            actual = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError as exc:
            raise RuntimeError(f"pinned dependency missing after install: {name}") from exc
        if actual != expected:
            raise RuntimeError(f"dependency version drift for {name}: expected {expected}, observed {actual}")
        installed[name] = actual
    return {
        "schema_version": "ds-lite.ci-dependency-install.v1",
        "status": "passed",
        "lock": lock.as_posix(),
        "package_count": len(installed),
        "versions": installed,
        "artifact_hashes_verified": False,
        "artifact_hash_note": "platform-specific wheel hashes are verified by release lock jobs; CI verifies exact pinned versions",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lock", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = install(args.lock)
    if args.output:
        if args.output.exists():
            raise SystemExit("refusing to overwrite dependency receipt")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
