from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "plugins" / "deepscientist-lite-core" / "controller"))

from ds_lite_control.failure_policy import FailureClassifier
from ds_lite_control.scheduler import DagScheduler
from ds_lite_control.store import ControlStore


def _write_once(path: Path, payload: dict) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=True, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--owner-id", required=True)
    args = parser.parse_args()
    store = ControlStore(args.project / ".ds-lite" / "control.sqlite3")
    scheduler = DagScheduler(
        store, FailureClassifier(seed=20260731), max_concurrency=2,
        retry_concurrency=1, lease_ttl_seconds=2,
    )
    try:
        recovered = scheduler.recover_expired(args.job_id, args.owner_id)
        claimed = scheduler.claim_ready(args.job_id, args.owner_id)
        active = [*recovered, *claimed]
        barrier = args.runtime / "crash-barrier.json"
        if not barrier.exists():
            if len(active) != 2:
                raise RuntimeError("first generation must own two gates")
            survivor = next(claim for claim in active if claim.work_item_id.endswith("gate-b"))
            interrupted = next(claim for claim in active if claim.work_item_id.endswith("gate-a"))
            scheduler.complete_gate(survivor, outcome="completed", evidence_hash="b" * 64)
            _write_once(barrier, {
                "controller_pid": os.getpid(), "interrupted_action_id": interrupted.action_id,
                "peak_concurrency": len(active), "fence_epoch": interrupted.fence_epoch,
            })
            while True:
                time.sleep(1)
        if len(recovered) != 1 or recovered[0].work_item_id != f"{args.job_id}-gate-a":
            raise RuntimeError("expired gate was not recovered exactly once")
        scheduler.complete_gate(recovered[0], outcome="completed", evidence_hash="a" * 64)
        _write_once(args.runtime / "completed.json", {
            "controller_pid": os.getpid(), "recovered_action_id": recovered[0].action_id,
            "fence_epoch": recovered[0].fence_epoch,
        })
        while True:
            time.sleep(1)
    finally:
        store.close()


if __name__ == "__main__":
    raise SystemExit(main())
