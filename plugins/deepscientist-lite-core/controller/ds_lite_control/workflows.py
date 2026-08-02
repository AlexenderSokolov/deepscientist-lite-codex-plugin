from __future__ import annotations

import hashlib

from .receipts import ReceiptStore
from .store import ControlStore


WORKFLOW_REGISTRY = {
    "reconcile_job_v1": {"version": 1},
    "run_action_v1": {"version": 1},
    "run_codex_action_v1": {"version": 1},
    "run_codex_action_v2": {"version": 2},
    "project_status_v1": {"version": 1},
    "schedule_job_v1": {"version": 1},
    "cooldown_gate_v1": {"version": 1},
    "reconcile_gate_v1": {"version": 1},
    "verify_gate_v1": {"version": 1},
    "review_gate_v1": {"version": 1},
    "aggregate_release_v1": {"version": 1},
}


def workflow_kind_for_action(action_kind: str, *, existing: str | None = None) -> str:
    if existing is not None:
        if existing not in WORKFLOW_REGISTRY:
            raise ValueError("unknown existing workflow kind")
        return existing
    if action_kind == "codex-turn-v2":
        return "run_codex_action_v2"
    if action_kind == "codex-turn":
        return "run_codex_action_v1"
    if action_kind == "fake-turn":
        return "run_action_v1"
    raise ValueError("unsupported action kind")


class ManagedController:
    """One bounded Phase 1 controller pass using fake-host evidence only."""

    def __init__(self, store: ControlStore, receipt_root, *, owner_id: str) -> None:
        self.store = store
        self.receipts = ReceiptStore(receipt_root, store)
        self.owner_id = owner_id

    def run_once(self, job_id: str, work_item_id: str, action_id: str) -> dict:
        epoch = self.store.create_job_work_item(job_id, work_item_id, self.owner_id)
        self.store.plan_attempt_action(
            job_id=job_id, work_item_id=work_item_id, attempt_id=f"attempt-{action_id}",
            action_id=action_id, kind="fake-turn", payload_hash=hashlib.sha256(action_id.encode()).hexdigest(),
            owner_id=self.owner_id, fence_epoch=epoch,
        )
        self.store.transition_outbox(action_id, "workflow_submitting", self.owner_id, epoch)
        self.store.attach_workflow(action_id, "run_action_v1", self.owner_id, epoch, "SUCCESS")
        self.store.record_host_event(
            event_id=f"terminal-{action_id}", action_id=action_id, event_type="terminal",
            observed_at="2026-07-31T00:00:00Z",
            payload_hash=hashlib.sha256(f"terminal:{action_id}".encode()).hexdigest(),
            owner_id=self.owner_id, fence_epoch=epoch,
        )
        payload = self.receipts.terminal_payload(action_id, self.owner_id, epoch)
        result = self.receipts.write_and_index(f"terminal-{action_id}", payload, self.owner_id, epoch)
        return result["receipt"]
