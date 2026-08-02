"""Run bounded Phase 5 real process-chaos samples without early-stop semantics."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def _write_once(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=True, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())


def evaluate_matrix(receipts: list[dict[str, Any]], expected_count: int) -> dict[str, Any]:
    identities = [str(item.get("sample_id", "")) for item in receipts]
    checks = {
        "sample_count": len(receipts) == expected_count,
        "unique_sample_identity": len(set(identities)) == expected_count and all(identities),
        "all_samples_passed": all(item.get("status") == "passed" for item in receipts),
    }
    return {
        "status": "passed" if all(checks.values()) else "failed",
        "checks": checks,
        "passed_count": sum(item.get("status") == "passed" for item in receipts),
        "failed_sample_ids": [
            str(item.get("sample_id", "unknown"))
            for item in receipts if item.get("status") != "passed"
        ],
        "release_allowed": False,
    }


def _command(args: argparse.Namespace, index: int, output: Path, runtime: Path) -> list[str]:
    sample_id = f"{args.scenario}-{index:02d}"
    if args.scenario == "controller":
        return [
            sys.executable, str(ROOT / "teaching" / "controller_broker_smoke.py"),
            "--codex-bin", str(args.codex_bin), "--schema-root", str(args.schema_root),
            "--workspace", str(args.workspace), "--runtime", str(runtime),
            "--output", str(output), "--journal-summary", str(output.with_name(output.stem + "-journal.json")),
            "--codex-version", args.codex_version, "--sample-id", sample_id, "--ambient-home",
        ]
    scenario = "app-server" if args.scenario == "app-server" else "controller-and-app-server"
    return [
        sys.executable, "-m", "teaching.control_plane_phase5_process_chaos", "run",
        "--scenario", scenario, "--sample-id", sample_id,
        "--codex-bin", str(args.codex_bin), "--schema-root", str(args.schema_root),
        "--codex-home", str(args.evidence_root / "unused-home"),
        "--workspace", str(args.workspace), "--runtime", str(runtime),
        "--output", str(output), "--model", args.model, "--timeout", str(args.timeout),
        "--ambient-home",
    ]


def run(args: argparse.Namespace) -> dict[str, Any]:
    if args.summary.exists():
        raise FileExistsError("chaos matrix summary already exists")
    receipts: list[dict[str, Any]] = []
    for index in range(args.start_index, args.start_index + args.count):
        stem = f"{args.scenario}-{index:02d}"
        output = args.evidence_root / f"{stem}.json"
        runtime = args.evidence_root / f"{stem}-runtime"
        completed = subprocess.run(
            _command(args, index, output, runtime), cwd=ROOT,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
        )
        if output.is_file():
            receipt = json.loads(output.read_text(encoding="utf-8"))
        else:
            receipt = {"sample_id": stem, "status": "failed", "failure_layer": "receipt-missing"}
        receipt = dict(receipt)
        receipt.setdefault("sample_id", stem)
        receipt["process_exit_code"] = completed.returncode
        receipts.append(receipt)
    result = evaluate_matrix(receipts, args.count)
    summary = {
        "schema_version": "ds-lite.phase5-chaos-matrix.v1",
        "scenario": args.scenario,
        "start_index": args.start_index,
        "sample_count": args.count,
        **result,
        "receipts": [
            {"sample_id": item["sample_id"], "status": item.get("status"),
             "process_exit_code": item["process_exit_code"]}
            for item in receipts
        ],
    }
    _write_once(args.summary, summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", choices=("controller", "app-server", "both"), required=True)
    parser.add_argument("--start-index", type=int, required=True)
    parser.add_argument("--count", type=int, required=True)
    parser.add_argument("--codex-bin", type=Path, required=True)
    parser.add_argument("--schema-root", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--evidence-root", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--codex-version", default="0.146.0")
    parser.add_argument("--model", default="gpt-5.6-sol")
    parser.add_argument("--timeout", type=float, default=90.0)
    args = parser.parse_args()
    try:
        result = run(args)
    except Exception as exc:
        result = {"status": "failed", "failure_layer": type(exc).__name__}
    print(json.dumps({"status": result["status"], "scenario": args.scenario}))
    return 0 if result["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
