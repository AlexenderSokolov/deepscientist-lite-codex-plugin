#!/usr/bin/env python3
"""Validate a post-release receipt without inferring any release gate."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create a DS Lite post-release receipt.")
    parser.add_argument("--tag", required=True)
    parser.add_argument("--marketplace", required=True)
    parser.add_argument("--cache", action="append", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    output = Path(args.output).expanduser().resolve()
    if output.exists():
        print(json.dumps({"status": "blocked", "reason": "output-exists"}))
        return 2
    try:
        marketplace = Path(args.marketplace).expanduser().resolve()
        cache_paths = [Path(item).expanduser().resolve() for item in args.cache]
        if not marketplace.is_file() or any(not path.exists() for path in cache_paths):
            raise OSError("marketplace or cache receipt is missing")
        payload = {
            "schema_version": "ds-lite.release-receipt.v1",
            "status": "passed",
            "tag": args.tag,
            "observed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "marketplace_sha256": hashlib.sha256(marketplace.read_bytes()).hexdigest(),
            "cache_receipts": [{"path": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()} for path in cache_paths],
            "extensions": {},
        }
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except (OSError, UnicodeError):
        print(json.dumps({"status": "blocked", "reason": "release-evidence-missing"}))
        return 2
    print(json.dumps({"status": "passed", "receipt": str(output)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
