from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _stamp(value: datetime) -> str:
    return _utc(value).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class FailureDecision:
    layer: str
    failure_class: str
    disposition: str
    signature: str
    impact_scope: str
    retry_delay_seconds: int
    next_eligible_at: str | None
    next_action: str


class FailureClassifier:
    """Normalize external observations without retaining provider text."""

    def __init__(self, *, seed: int = 0) -> None:
        self.seed = seed

    def classify(
        self,
        *,
        layer: str,
        attempt: int,
        now: datetime,
        http_status: int | None = None,
        retry_after_seconds: int | None = None,
    ) -> FailureDecision:
        normalized = layer.strip().casefold() or "unknown"
        signature = hashlib.sha256(
            f"{normalized}:{http_status or 0}".encode("ascii", "strict")
        ).hexdigest()

        if normalized in {"auth", "authorization", "hook-trust", "permission", "trust"}:
            return FailureDecision(
                normalized, "authorization", "awaiting_user_action", signature,
                "gate", 0, None, "await-user-action",
            )
        if normalized in {"ambiguous", "ambiguous-transport", "stream-disconnect"}:
            return FailureDecision(
                normalized, "ambiguous", "reconciling", signature,
                "gate", 0, None, "reconcile-same-identity",
            )
        if normalized in {"scientific-negative", "valid-negative"}:
            return FailureDecision(
                normalized, "scientific-result", "valid_negative", signature,
                "gate", 0, None, "create-next-iteration",
            )

        retryable = (
            http_status in {408, 429}
            or (http_status is not None and 500 <= http_status <= 599)
            or normalized in {"network", "timeout", "provider-unavailable", "external-transient"}
        )
        if retryable:
            failure_class = "rate-limit" if http_status == 429 else "transient"
            if isinstance(retry_after_seconds, int) and 0 <= retry_after_seconds <= 3600:
                delay = retry_after_seconds
            else:
                ceiling = min(300, 2 ** max(0, min(attempt, 8)))
                jitter = random.Random(f"{self.seed}:{signature}:{attempt}")
                delay = max(1, int(jitter.uniform(0, ceiling)))
            eligible = _stamp(_utc(now) + timedelta(seconds=delay))
            return FailureDecision(
                normalized, failure_class, "cooldown", signature,
                "gate", delay, eligible, "retry-same-identity",
            )

        return FailureDecision(
            normalized, "deterministic", "terminal_failure", signature,
            "gate", 0, None, "freeze-gate",
        )
