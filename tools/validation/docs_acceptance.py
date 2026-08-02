#!/usr/bin/env python3
"""Validate the release-facing DS Lite documentation surface into one fresh receipt."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


REQUIRED = (
    "PROJECT.md",
    "README.md",
    "README.zh.md",
    "docs/implementation.zh.md",
    "docs/openscience-worker-handoff.zh.md",
    "docs/maintainers/release-checklist.md",
)
MARKERS = {
    "docs/maintainers/release-checklist.md": ("formal-release-gate.v2", "fresh Desktop", "OpenScience"),
    "docs/openscience-worker-handoff.zh.md": ("OpenScience", "approval"),
}


def evaluate(root: Path) -> tuple[dict, int]:
    records = []
    passed = True
    for relative in REQUIRED:
        path = root / relative
        try:
            raw = path.read_bytes()
            text = raw.decode("utf-8-sig")
            markers = list(MARKERS.get(relative, ()))
            marker_ok = all(marker.lower() in text.lower() for marker in markers)
            status = "passed" if text.strip() and marker_ok else "blocked"
        except (OSError, UnicodeError):
            raw = b""; status = "blocked"; marker_ok = False
        passed = passed and status == "passed"
        records.append({"path": relative, "status": status, "sha256": hashlib.sha256(raw).hexdigest(), "required_markers_observed": marker_ok})
    result = {"schema_version": "ds-lite.docs-acceptance.v1", "status": "passed" if passed else "blocked",
              "failure_layer": "none" if passed else "documentation-completeness", "observed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
              "documents": records, "release_profile": "ds-lite-0.8.1-complete", "raw_document_content_persisted": False,
              "next_action": "formal release aggregation" if passed else "repair the blocked documentation surface"}
    return result, 0 if passed else 2


def main() -> int:
    parser = argparse.ArgumentParser(description="Write a fresh DS Lite documentation acceptance receipt.")
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        print(json.dumps({"status": "blocked", "reason": "output-exists"}))
        return 2
    result, code = evaluate(args.root.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"]}))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
