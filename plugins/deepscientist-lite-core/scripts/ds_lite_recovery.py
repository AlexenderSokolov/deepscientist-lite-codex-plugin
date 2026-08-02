#!/usr/bin/env python3
"""Redacted failure classification shared by DS Lite control surfaces."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any


RETRYABLE_HTTP = {408, 429, 500, 502, 503, 504}
USER_ACTION_HTTP = {401, 402, 403}
PROTOCOL_HTTP = {400, 422}


def classify_failure(failure_layer: object, *, http_status: Any = None, message: object = "") -> dict[str, Any]:
    """Classify without returning raw provider or transport text."""
    layer = str(failure_layer or "unknown").casefold()
    text = f"{layer} {str(message or '').casefold()}"
    status = http_status if isinstance(http_status, int) and 100 <= http_status <= 599 else None
    if status in USER_ACTION_HTTP or any(item in text for item in ("quota", "credit", "billing", "payment", "authorization", "authentication", "auth")):
        return {"recovery_class": "awaiting-user-action", "failure_layer": "provider-user-action", "http_status": status, "next_automatic_action": "await-user-action"}
    if status in RETRYABLE_HTTP or any(item in text for item in ("network", "dns", "reset", "connection", "tls", "timeout", "transport")):
        return {"recovery_class": "retryable", "failure_layer": "external-transient", "http_status": status, "next_automatic_action": "retry-same-identity"}
    if status in PROTOCOL_HTTP or any(item in text for item in ("protocol", "malformed", "invalid response", "session-drift", "session-id-not-observed", "runner-owner-busy", "hook-trust")):
        return {"recovery_class": "terminal", "failure_layer": "protocol-or-session", "http_status": status, "next_automatic_action": "freeze-identity-and-diagnose"}
    return {"recovery_class": "diagnose-once", "failure_layer": "external-unknown", "http_status": status, "next_automatic_action": "diagnose-then-retry-once"}


def retry_schedule(attempt: int, *, retry_after_seconds: Any = None, now: datetime | None = None) -> dict[str, Any]:
    retry_after = retry_after_seconds if isinstance(retry_after_seconds, int) and 0 <= retry_after_seconds <= 300 else None
    delay = retry_after if retry_after is not None else min(300, 2 ** max(0, min(attempt - 1, 7)))
    observed = now or datetime.now(timezone.utc)
    return {"retry_after_seconds": retry_after, "retry_delay_seconds": delay, "next_retry_at": (observed + timedelta(seconds=delay)).isoformat().replace("+00:00", "Z")}
