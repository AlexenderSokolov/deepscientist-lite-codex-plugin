#!/usr/bin/env python3
"""Create a write-once package identity projection across release boundaries."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

try:
    from package_identity import tree_digest
except ModuleNotFoundError:
    from tools.validation.package_identity import tree_digest


def build_identity(*, source: Path, candidate: Path | None = None, cache: Path | None = None,
                   loaded_runtime: str | None = None, tag: str | None = None,
                   commit: str | None = None, candidate_receipt: Path | None = None,
                   cache_receipt: Path | None = None, host_receipt: Path | None = None) -> dict:
    source = source.resolve()
    candidate_path = candidate_receipt.resolve() if candidate_receipt else None
    cache_receipt_path = cache_receipt.resolve() if cache_receipt else None
    host_receipt_path = host_receipt.resolve() if host_receipt else None

    def _json(path: Path | None) -> dict | None:
        if path is None or not path.is_file():
            return None
        try:
            value = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            return None
        return value if isinstance(value, dict) else None

    def _file_sha(path: Path | None) -> str | None:
        if path is None or not path.is_file():
            return None
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    candidate_payload = _json(candidate_path)
    host_payload = _json(host_receipt_path)
    candidate_digest = (
        candidate_payload.get("candidate_digest")
        if candidate_payload and isinstance(candidate_payload.get("candidate_digest"), str)
        else tree_digest(candidate.resolve()) if candidate and candidate.is_dir() else None
    )
    cache_digest = tree_digest(cache.resolve()) if cache and cache.is_dir() else None
    return {
        "schema_version": "ds-lite.package-identity.v1",
        "observed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "status": {
            "source": "observed",
            "candidate": "observed" if candidate_digest else "not-observed",
            "host": (
                "verified"
                if host_payload and host_payload.get("status") == "passed"
                else "not-verified"
            ),
            "publication": "not-authorized",
            "formal_gate": "not-verified",
        },
        "tag": tag,
        "commit": commit,
        "source_digest": tree_digest(source),
        "candidate_digest": candidate_digest,
        "candidate_receipt_sha256": _file_sha(candidate_path),
        "cache_digest": cache_digest,
        "cache_receipt_sha256": _file_sha(cache_receipt_path),
        "host_receipt_sha256": _file_sha(host_receipt_path),
        "host_status": host_payload.get("status") if host_payload else None,
        "loaded_runtime": loaded_runtime,
        "release_allowed": False,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--candidate", type=Path)
    parser.add_argument("--cache", type=Path)
    parser.add_argument("--loaded-runtime")
    parser.add_argument("--tag")
    parser.add_argument("--commit")
    parser.add_argument("--candidate-receipt", type=Path)
    parser.add_argument("--cache-receipt", type=Path)
    parser.add_argument("--host-receipt", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    payload = json.dumps(build_identity(source=args.source, candidate=args.candidate, cache=args.cache,
                                        loaded_runtime=args.loaded_runtime, tag=args.tag, commit=args.commit,
                                        candidate_receipt=args.candidate_receipt,
                                        cache_receipt=args.cache_receipt,
                                        host_receipt=args.host_receipt),
                         ensure_ascii=True, indent=2) + "\n"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(payload)
    print(json.dumps({"status": "passed", "source_digest": json.loads(payload)["source_digest"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
