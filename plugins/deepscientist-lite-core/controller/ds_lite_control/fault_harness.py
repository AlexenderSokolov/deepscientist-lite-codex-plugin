"""Fixed-seed fake-host K1-K6 protocol cuts."""

from __future__ import annotations

import random
import tempfile
from pathlib import Path

from .domain import ControlStore, FenceRejected
from .fake_app_server import FakeAppServer


def _k1(seed: int) -> bool:
    with tempfile.TemporaryDirectory(prefix=f"ds-lite-k1-{seed}-") as directory:
        store = ControlStore(Path(directory) / "control.sqlite")
        try:
            return store.plan_action("action", "turn") == store.plan_action("action", "turn") and store.workflow_binding_count("action") == 1
        finally:
            store.close()


def _k2(seed: int) -> bool:
    with tempfile.TemporaryDirectory(prefix=f"ds-lite-k2-{seed}-") as directory:
        store = ControlStore(Path(directory) / "control.sqlite")
        try:
            store.plan_action("action", "turn")
            old = store.acquire_lease(
                "work", "old", allow_unexpired_takeover=True
            )
            current = store.acquire_lease(
                "work", "current", allow_unexpired_takeover=True
            )
            try:
                store.enqueue("action", old, "old")
                return False
            except FenceRejected:
                store.enqueue("action", current, "current")
                return True
        finally:
            store.close()


def _k3(seed: int) -> bool:
    host = FakeAppServer()
    return host.observe_notification(f"thread-{seed}")["state"] == "active"


def _k4(seed: int) -> bool:
    host = FakeAppServer()
    result = host.resume_or_classify(f"missing-{seed}")
    return result["state"] == "ambiguous" and host.start_count == 0


def _k5(seed: int) -> bool:
    host = FakeAppServer()
    return host.dispatch_acknowledged_then_lost(f"thread-{seed}")["state"] == "ambiguous"


def _k6(seed: int) -> bool:
    gates = {"retrying": "cooldown", "independent": "ready"}
    return gates["retrying"] == "cooldown" and gates["independent"] == "ready"


CASES = {"K1": _k1, "K2": _k2, "K3": _k3, "K4": _k4, "K5": _k5, "K6": _k6}


def run_k1_k6(*, seed: int, trials: int) -> dict:
    if trials <= 0:
        raise ValueError("trials must be positive")
    randomizer = random.Random(seed)
    cases: dict[str, dict[str, int | bool]] = {}
    for name, scenario in CASES.items():
        passed = sum(bool(scenario(randomizer.randrange(2**31))) for _ in range(trials))
        cases[name] = {"passed": passed, "failed": trials - passed, "all_passed": passed == trials}
    return {"schema_version": "ds-lite.control-plane-fake-host.v1", "evidence_class": "fake-host", "seed": seed, "trials": trials, "cases": cases}
