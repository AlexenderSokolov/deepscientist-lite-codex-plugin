#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check the Academic pack's Core compatibility.")
    parser.add_argument("--core-root")
    args = parser.parse_args(argv)
    package_root = Path(__file__).resolve().parents[1]
    compatibility = json.loads((package_root / "compatibility.json").read_text(encoding="utf-8"))
    raw_core = args.core_root or os.environ.get("DS_LITE_CORE_ROOT", "").strip()
    result = {
        "schema_version": "ds-lite.pack-doctor.v1",
        "pack": compatibility["pack"],
        "version": compatibility["version"],
        "status": "blocked",
        "required": compatibility["requires"],
    }
    if not raw_core:
        result["reason"] = "core-root-not-provided"
        print(json.dumps(result, ensure_ascii=False))
        return 2
    try:
        core_manifest = json.loads(
            (Path(raw_core).expanduser().resolve() / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
        )
    except (OSError, UnicodeError, json.JSONDecodeError):
        result["reason"] = "core-manifest-unavailable"
        print(json.dumps(result, ensure_ascii=False))
        return 2
    observed = {"plugin": core_manifest.get("name"), "version": core_manifest.get("version")}
    result["observed"] = observed
    if observed != compatibility["requires"]:
        result["reason"] = "incompatible-core"
        print(json.dumps(result, ensure_ascii=False))
        return 2
    result["status"] = "passed"
    result["reason"] = "compatible-core-observed"
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
