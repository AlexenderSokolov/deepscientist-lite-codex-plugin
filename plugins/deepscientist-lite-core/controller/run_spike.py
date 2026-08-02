"""Write one Phase 0.5 fake-host protocol-spike receipt."""

from __future__ import annotations

import argparse
import importlib
import json
import sys
from pathlib import Path

from ds_lite_control.fault_harness import run_k1_k6


def write_once(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--seed", type=int, default=20260731)
    parser.add_argument("--trials", type=int, default=100)
    parser.add_argument("--dependency-root", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        print(json.dumps({"status": "blocked", "reason": "output-exists"}))
        return 2
    sys.path.insert(0, str(args.dependency_root.resolve()))
    try:
        module = importlib.import_module("dbos")
        dbos_imported = bool(getattr(module, "__file__", ""))
    except ImportError:
        dbos_imported = False
    result = run_k1_k6(seed=args.seed, trials=args.trials)
    result.update({
        "dbos_dependency_imported": dbos_imported,
        "real_app_server_status": "not-observed",
        "release_allowed": False,
        "status": "passed" if dbos_imported and all(case["all_passed"] for case in result["cases"].values()) else "blocked",
    })
    write_once(args.output.resolve(), result)
    print(json.dumps({"status": result["status"], "evidence_class": result["evidence_class"]}))
    return 0 if result["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
