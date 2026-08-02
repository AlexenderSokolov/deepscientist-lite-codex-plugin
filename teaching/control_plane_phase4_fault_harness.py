"""External-process Phase 4 write-once receipt fault matrix."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


CONTROLLER_ROOT = (
    Path(__file__).resolve().parents[1]
    / "plugins" / "deepscientist-lite-core" / "controller"
)
if str(CONTROLLER_ROOT) not in sys.path:
    sys.path.insert(0, str(CONTROLLER_ROOT))

from ds_lite_control.evidence import EvidenceManager, file_hash
from ds_lite_control.errors import FenceRejected, IntegrityIncident
from ds_lite_control.release import StrictReleaseAggregate
from ds_lite_control.review import ReviewCoordinator
from ds_lite_control.store import ControlStore
from ds_lite_control.verification import DeterministicVerifier


CASES = (
    "verifier-receipt-before-index",
    "review-terminal-before-sidecar",
    "sidecar-before-index",
    "aggregate-receipt-before-index",
)

POLICY = {
    "schema_version": "ds-lite.gate-policy.v1",
    "policy_id": "phase4-fault-policy-v1",
    "minimum_evidence_class": "offline",
    "required_artifacts": [{
        "path": "result.json",
        "schema_version": "ds-lite.phase4-fault-fixture.v1",
        "required_fields": {"measurement": 42},
    }],
}

SIDECAR = {
    "schema_version": "ds-lite.review-sidecar.v1",
    "verdict": "accept",
    "finding_codes": [],
    "evidence_refs": ["result.json"],
}

PROFILE = {
    "schema_version": "ds-lite.release-profile.v1",
    "profile_id": "phase4-project-profile",
    "required_gates": ["phase5-real-host"],
    "fixture_only": False,
}


def _write_once(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=True, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())


def _install_index_cut(store: ControlStore) -> None:
    store.connection.execute(
        "CREATE TRIGGER phase4_fault_receipt_index BEFORE INSERT ON receipt_index "
        "BEGIN SELECT RAISE(ABORT, 'phase4 receipt index cut'); END"
    )
    store.connection.commit()


def _remove_index_cut(store: ControlStore) -> None:
    store.connection.execute("DROP TRIGGER IF EXISTS phase4_fault_receipt_index")
    store.connection.commit()


def _setup(root: Path, identity: str, *, verifier: bool, review: bool) -> dict[str, Any]:
    store = ControlStore(root / "control.sqlite3")
    try:
        epoch = store.create_job_work_item(
            "job-1", "gate-a", "owner-old", lease_ttl_seconds=60
        )
        artifacts = root / "artifacts"
        artifacts.mkdir()
        (artifacts / "result.json").write_text(
            json.dumps({
                "schema_version": "ds-lite.phase4-fault-fixture.v1",
                "identity": identity,
                "measurement": 42,
                "passed": True,
                "release_allowed": True,
            }, ensure_ascii=True, sort_keys=True),
            encoding="utf-8",
        )
        manifest = EvidenceManager(
            store, root / "evidence", root / "private-spool"
        ).freeze(
            "job-1", "gate-a", artifacts, POLICY, evidence_class="offline",
            owner_id="owner-old", fence_epoch=epoch,
        )
        context: dict[str, Any] = {
            "epoch": epoch,
            "evidence_set_id": manifest["evidence_set_id"],
            "manifest_hash": manifest["manifest_hash"],
        }
        if verifier:
            receipt = DeterministicVerifier(store, root / "receipts").verify(
                "gate-a", manifest["evidence_set_id"], POLICY,
                owner_id="owner-old", fence_epoch=epoch,
            )
            context["verifier_id"] = receipt["verifier_id"]
        if review:
            coordinator = ReviewCoordinator(store, root / "receipts")
            request = coordinator.prepare(
                "gate-a", manifest["evidence_set_id"], context["verifier_id"],
                schema_digest="s" * 64, model="gpt-5.6-sol",
                owner_id="owner-old", fence_epoch=epoch,
            )
            coordinator.bind_thread(
                request["review_id"], f"review-thread-{identity}",
                worker_thread_ids=set(), owner_id="owner-old", fence_epoch=epoch,
            )
            context["review_id"] = request["review_id"]
            context["reviewer_turn_id"] = f"review-turn-{identity}"
        return context
    finally:
        store.close()


def _child_cut(case: str, root: Path, marker: Path, identity: str) -> int:
    root.mkdir(parents=True, exist_ok=False)
    context = _setup(
        root, identity,
        verifier=case != "verifier-receipt-before-index",
        review=case in {"review-terminal-before-sidecar", "sidecar-before-index"},
    )
    store = ControlStore(root / "control.sqlite3")
    try:
        if case == "verifier-receipt-before-index":
            _install_index_cut(store)
            try:
                DeterministicVerifier(store, root / "receipts").verify(
                    "gate-a", context["evidence_set_id"], POLICY,
                    owner_id="owner-old", fence_epoch=context["epoch"],
                )
            except sqlite3.DatabaseError:
                pass
        elif case == "review-terminal-before-sidecar":
            store.connection.execute("BEGIN IMMEDIATE")
            store.connection.execute(
                "UPDATE review_requests SET state='observing',reviewer_turn_id=? WHERE review_id=?",
                (context["reviewer_turn_id"], context["review_id"]),
            )
            store.connection.commit()
        elif case == "sidecar-before-index":
            _install_index_cut(store)
            try:
                ReviewCoordinator(store, root / "receipts").record_result(
                    context["review_id"], SIDECAR,
                    post_manifest_hash=context["manifest_hash"],
                    reviewer_turn_id=context["reviewer_turn_id"],
                    owner_id="owner-old", fence_epoch=context["epoch"],
                )
            except sqlite3.DatabaseError:
                pass
        elif case == "aggregate-receipt-before-index":
            context["job_epoch"] = store.acquire_lease("job-1", "owner-old")
            _install_index_cut(store)
            try:
                StrictReleaseAggregate(store, root / "receipts").materialize(
                    "job-1", PROFILE, owner_id="owner-old",
                    fence_epoch=context["job_epoch"],
                )
            except sqlite3.DatabaseError:
                pass
        else:
            raise ValueError(case)
    finally:
        store.close()
    _write_once(root / "context.json", context)
    _write_once(marker, {"case": case, "identity": identity, "cut_observed": True})
    while True:
        time.sleep(1)


def _command(python_bin: Path, case: str, root: Path, marker: Path, identity: str) -> list[str]:
    return [
        str(python_bin.resolve()), str(Path(__file__).resolve()),
        "--child-case", case, "--case-root", str(root), "--marker", str(marker),
        "--identity", identity,
    ]


def _kill_at_barrier(command: list[str], marker: Path, env: dict[str, str], timeout: float) -> bool:
    process = subprocess.Popen(
        command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env
    )
    deadline = time.monotonic() + timeout
    while not marker.is_file() and process.poll() is None and time.monotonic() < deadline:
        time.sleep(0.005)
    observed = marker.is_file()
    if process.poll() is None:
        process.kill()
    process.communicate(timeout=10)
    return observed and process.returncode is not None


def _receipt_state(root: Path) -> tuple[dict[str, str], int]:
    files = {
        path.name: file_hash(path) for path in sorted((root / "receipts").glob("*.json"))
    }
    store = ControlStore(root / "control.sqlite3")
    try:
        indexed = int(store.connection.execute("SELECT COUNT(*) FROM receipt_index").fetchone()[0])
    finally:
        store.close()
    return files, indexed


def _recover(case: str, root: Path) -> dict[str, bool]:
    context = json.loads((root / "context.json").read_text(encoding="utf-8"))
    before_files, before_index = _receipt_state(root)
    store = ControlStore(root / "control.sqlite3")
    resource_id = "job-1" if case == "aggregate-receipt-before-index" else "gate-a"
    try:
        _remove_index_cut(store)
        new_epoch = store.acquire_lease(
            resource_id, "owner-new", allow_unexpired_takeover=True
        )
        try:
            store.heartbeat_lease(
                resource_id, "owner-old",
                int(context.get("job_epoch", context["epoch"])), ttl_seconds=60,
            )
            stale_rejected = False
        except FenceRejected:
            stale_rejected = True

        if case == "verifier-receipt-before-index":
            operation = lambda: DeterministicVerifier(store, root / "receipts").verify(
                "gate-a", context["evidence_set_id"], POLICY,
                owner_id="owner-new", fence_epoch=new_epoch,
            )
        elif case in {"review-terminal-before-sidecar", "sidecar-before-index"}:
            operation = lambda: ReviewCoordinator(store, root / "receipts").record_result(
                context["review_id"], SIDECAR,
                post_manifest_hash=context["manifest_hash"],
                reviewer_turn_id=context["reviewer_turn_id"],
                owner_id="owner-new", fence_epoch=new_epoch,
            )
        else:
            operation = lambda: StrictReleaseAggregate(store, root / "receipts").materialize(
                "job-1", PROFILE, owner_id="owner-new", fence_epoch=new_epoch,
            )
        first = operation()
        after_first_files, after_first_index = _receipt_state(root)
        try:
            second = operation()
        except IntegrityIncident:
            second = None
        after_second_files, after_second_index = _receipt_state(root)
        receipt_name = f"{first['receipt_id']}.json"
        receipt_was_preexisting = receipt_name in before_files
        return {
            "receipt_file_preserved": (
                after_first_files.get(receipt_name) == after_second_files.get(receipt_name)
                and (not receipt_was_preexisting
                     or before_files[receipt_name] == after_first_files.get(receipt_name))
            ),
            "index_reconciled": after_first_index == before_index + 1,
            "idempotent_replay": (
                second is not None
                and first["receipt_hash"] == second["receipt_hash"]
                and after_first_files == after_second_files
                and after_first_index == after_second_index
            ),
            "stale_fence_rejected": stale_rejected,
        }
    finally:
        store.close()


def _trial(
    case: str, root: Path, identity: str, python_bin: Path,
    env: dict[str, str], timeout: float,
) -> dict[str, bool]:
    marker = root.parent / f"{root.name}.barrier.json"
    killed = _kill_at_barrier(
        _command(python_bin, case, root, marker, identity), marker, env, timeout
    )
    if not killed:
        return {
            "receipt_file_preserved": False, "index_reconciled": False,
            "idempotent_replay": False, "stale_fence_rejected": False,
        }
    return _recover(case, root)


def run_matrix(
    workdir: Path,
    output: Path,
    *,
    python_bin: Path,
    seed: int,
    trials: int,
    timeout: float = 20,
) -> dict[str, Any]:
    if workdir.exists() or output.exists():
        raise FileExistsError("phase4 fault evidence paths must be new")
    if trials <= 0:
        raise ValueError("trials must be positive")
    workdir.mkdir(parents=True, exist_ok=False)
    env = os.environ.copy()
    paths = [str(CONTROLLER_ROOT)]
    if env.get("PYTHONPATH"):
        paths.append(env["PYTHONPATH"])
    env["PYTHONPATH"] = os.pathsep.join(paths)
    randomizer = random.Random(seed)
    cases: dict[str, Any] = {}
    for case in CASES:
        observations: list[dict[str, bool]] = []
        identities: list[str] = []
        for trial in range(trials):
            identity = f"phase4-{randomizer.randrange(2**63):016x}"
            identities.append(identity)
            observations.append(_trial(
                case, workdir / case / f"trial-{trial:03d}", identity,
                python_bin, env, timeout,
            ))
        passed = sum(all(item.values()) for item in observations)
        cases[case] = {
            "passed": passed,
            "failed": trials - passed,
            "all_passed": passed == trials,
            "receipt_file_preserved": all(item["receipt_file_preserved"] for item in observations),
            "index_reconciled": all(item["index_reconciled"] for item in observations),
            "idempotent_replay": all(item["idempotent_replay"] for item in observations),
            "stale_fence_rejected": all(item["stale_fence_rejected"] for item in observations),
            "identity_digest": hashlib.sha256("".join(identities).encode()).hexdigest(),
            "evidence_class": "sqlite-filesystem-external-process",
        }
    result = {
        "schema_version": "ds-lite.phase4-fault-matrix.v1",
        "seed": seed,
        "trials": trials,
        "cases": cases,
        "external_process_termination": True,
        "status": "passed" if all(item["all_passed"] for item in cases.values()) else "failed",
        "release_allowed": False,
    }
    _write_once(output, result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workdir", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--python-bin", type=Path, default=Path(sys.executable))
    parser.add_argument("--seed", type=int, default=20260801)
    parser.add_argument("--trials", type=int, default=100)
    parser.add_argument("--timeout", type=float, default=20)
    parser.add_argument("--child-case", choices=CASES)
    parser.add_argument("--case-root", type=Path)
    parser.add_argument("--marker", type=Path)
    parser.add_argument("--identity")
    args = parser.parse_args()
    if args.child_case:
        return _child_cut(
            args.child_case, args.case_root.resolve(), args.marker.resolve(), args.identity
        )
    if args.workdir is None or args.output is None:
        parser.error("--workdir and --output are required")
    result = run_matrix(
        args.workdir.resolve(), args.output.resolve(), python_bin=args.python_bin,
        seed=args.seed, trials=args.trials, timeout=args.timeout,
    )
    print(json.dumps({"status": result["status"], "trials": args.trials}))
    return 0 if result["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
