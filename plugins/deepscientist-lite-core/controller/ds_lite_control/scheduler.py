from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from .failure_policy import FailureClassifier, FailureDecision
from .store import ControlStore


@dataclass(frozen=True)
class GateClaim:
    job_id: str
    work_item_id: str
    owner_id: str
    fence_epoch: int
    attempt_number: int
    attempt_id: str
    action_id: str


class DagScheduler:
    def __init__(
        self,
        store: ControlStore,
        classifier: FailureClassifier,
        *,
        clock: Callable[[], datetime] | None = None,
        max_concurrency: int = 2,
        retry_concurrency: int = 1,
        lease_ttl_seconds: int = 60,
    ) -> None:
        self.store = store
        self.classifier = classifier
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.max_concurrency = max_concurrency
        self.retry_concurrency = retry_concurrency
        self.lease_ttl_seconds = lease_ttl_seconds

    def register_job(
        self, job_id: str, gates: list[dict], dependencies: list[dict[str, str]]
    ) -> None:
        self.store.register_job_graph(job_id, gates, dependencies)

    def claim_ready(self, job_id: str, owner_id: str) -> list[GateClaim]:
        self.store.assert_dispatch_allowed()
        rows = self.store.claim_ready_items(
            job_id, owner_id, max_concurrency=self.max_concurrency,
            retry_concurrency=self.retry_concurrency,
            lease_ttl_seconds=self.lease_ttl_seconds,
        )
        return [GateClaim(**row) for row in rows]

    def recover_expired(self, job_id: str, owner_id: str) -> list[GateClaim]:
        rows = self.store.recover_expired_running_items(
            job_id, owner_id, lease_ttl_seconds=self.lease_ttl_seconds,
        )
        return [GateClaim(**row) for row in rows]

    def record_failure(
        self,
        claim: GateClaim,
        *,
        layer: str,
        evidence_hash: str,
        http_status: int | None = None,
        retry_after_seconds: int | None = None,
    ) -> FailureDecision:
        decision = self.classifier.classify(
            layer=layer, http_status=http_status, retry_after_seconds=retry_after_seconds,
            attempt=claim.attempt_number, now=self.clock(),
        )
        self.store.apply_failure(
            claim.work_item_id, claim.owner_id, claim.fence_epoch,
            claim.attempt_number, decision, evidence_hash,
        )
        return decision

    def complete_gate(
        self, claim: GateClaim, *, outcome: str, evidence_hash: str
    ) -> str | None:
        return self.store.complete_work_item(
            claim.work_item_id, claim.owner_id, claim.fence_epoch,
            outcome=outcome, evidence_hash=evidence_hash,
        )

    def requeue_due(self, job_id: str) -> int:
        return self.store.requeue_due(job_id)

    def create_context_handoff(
        self, claim: GateClaim, *, state_pack_hash: str, evidence_hash: str
    ) -> str:
        return self.store.create_context_handoff(
            claim.attempt_id, claim.owner_id, claim.fence_epoch,
            state_pack_hash=state_pack_hash, evidence_hash=evidence_hash,
        )
