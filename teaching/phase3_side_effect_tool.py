from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path


def record_side_effect(root: Path) -> dict[str, str]:
    root = root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    journal = root / "side-effect-invocations.jsonl"
    event = {
        "schema_version": "ds-lite.phase3-side-effect.v1",
        "observed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    with journal.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(event, ensure_ascii=True, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    marker = root / "side-effect-marker.txt"
    with marker.open("x", encoding="ascii", newline="\n") as handle:
        handle.write("phase3-once\n")
        handle.flush()
        os.fsync(handle.fileno())
    return {"status": "created", "marker": marker.name}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = record_side_effect(args.root)
    except FileExistsError:
        print(json.dumps({"status": "duplicate-rejected"}, ensure_ascii=True))
        return 3
    print(json.dumps(result, ensure_ascii=True, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
