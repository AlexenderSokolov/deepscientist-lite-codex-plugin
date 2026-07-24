#!/usr/bin/env python3
"""Reduce transport and subprocess observations without retaining raw stderr."""

from __future__ import annotations

import hashlib
import re
from typing import Any


SCHEMA_VERSION = "ds-lite.transport-diagnostic.v1"
ALLOWED_PROVIDER_CODES = {
    "authentication_error",
    "invalid_api_key",
    "invalid_response",
    "model_not_found",
    "rate_limit_exceeded",
    "server_error",
    "service_unavailable",
}
ALLOWED_PROVIDER_TYPES = {
    "authentication_error",
    "invalid_request_error",
    "permission_denied",
    "rate_limit_exceeded",
    "model_not_found",
    "server_error",
    "service_unavailable",
}
HTTP_STATUS = re.compile(r"\b(?:http(?:/[0-9.]+)?\s*)?([1-5][0-9]{2})\b", re.IGNORECASE)
ERROR_CODE = re.compile(r"\b(?:error[_ -]?code|code)\s*[:=]\s*['\"]?([A-Za-z0-9_.-]{1,64})", re.IGNORECASE)


class TransportDiagnosticReducer:
    """Hash stderr while retaining only allow-listed diagnostic facts."""

    def __init__(self) -> None:
        self.digest = hashlib.sha256()
        self.line_count = 0
        self.legacy_categories: set[str] = set()
        self.failure_classes: set[str] = set()
        self.http_statuses: list[int] = []
        self.provider_codes: list[str] = []
        self.provider_types: list[str] = []
        self.connection_state = "unknown"
        self.response_header_state = "unknown"
        self.structured_error_count = 0
        self.structured_error_sources: set[str] = set()

    def consume(self, line: str) -> None:
        self.digest.update(line.encode("utf-8", errors="replace"))
        self.line_count += 1
        self._consume_evidence(line)

    def consume_structured_error(
        self,
        message: str,
        source: str,
        *,
        provider_code: str | None = None,
        provider_type: str | None = None,
        http_status: int | None = None,
    ) -> None:
        """Classify a JSONL error message without retaining it or calling it stderr."""
        normalized_source = source if source in {"error", "response.failed", "turn.failed"} else "unknown"
        self.structured_error_count += 1
        self.structured_error_sources.add(normalized_source)
        if isinstance(http_status, int) and 100 <= http_status <= 599:
            self.http_statuses.append(http_status)
            self.connection_state = "established"
            self.response_header_state = "received"
        if isinstance(provider_code, str) and provider_code:
            normalized_code = self._normalize_allowed(provider_code, ALLOWED_PROVIDER_CODES)
            self.provider_codes.append(normalized_code)
            if normalized_code in {"invalid_api_key", "authentication_error"}:
                self.legacy_categories.add("authentication")
                self.failure_classes.add("auth")
            elif normalized_code == "rate_limit_exceeded":
                self.legacy_categories.add("rate-limit")
                self.failure_classes.add("rate-limit")
            elif normalized_code in {"invalid_response", "model_not_found"}:
                self.legacy_categories.add("transport")
                self.failure_classes.add("protocol")
        if isinstance(provider_type, str) and provider_type:
            normalized_type = self._normalize_allowed(provider_type, ALLOWED_PROVIDER_TYPES)
            self.provider_types.append(normalized_type)
            if normalized_type in {"authentication_error", "permission_denied"}:
                self.legacy_categories.add("authentication")
                self.failure_classes.add("auth")
            elif normalized_type == "rate_limit_exceeded":
                self.legacy_categories.add("rate-limit")
                self.failure_classes.add("rate-limit")
            elif normalized_type in {"invalid_request_error", "model_not_found"}:
                self.legacy_categories.add("transport")
                self.failure_classes.add("protocol")
        self._consume_evidence(message)

    @staticmethod
    def _normalize_allowed(value: str, allowed: set[str]) -> str:
        normalized = value.lower().replace("-", "_").replace(".", "_")
        return normalized if normalized in allowed else "unrecognized"

    def _consume_evidence(self, line: str) -> None:
        lowered = line.lower()

        statuses = [int(value) for value in HTTP_STATUS.findall(lowered)]
        if statuses:
            self.http_statuses.extend(statuses)
            self.connection_state = "established"
            self.response_header_state = "received"

        for value in ERROR_CODE.findall(line):
            normalized = value.lower().replace("-", "_").replace(".", "_")
            self.provider_codes.append(normalized if normalized in ALLOWED_PROVIDER_CODES else "unrecognized")
        if not self.provider_codes:
            for code in sorted(ALLOWED_PROVIDER_CODES):
                if code in lowered:
                    self.provider_codes.append(code)
                    break

        if any(term in lowered for term in ("authentication", "unauthorized", "invalid api key", "invalid_api_key")) or 401 in statuses:
            self.legacy_categories.add("authentication")
            self.failure_classes.add("auth")
        if 403 in statuses:
            self.legacy_categories.add("authentication")
            self.failure_classes.add("auth")
        if any(term in lowered for term in ("rate limit", "rate_limit", "too many requests")) or 429 in statuses:
            self.legacy_categories.add("rate-limit")
            self.failure_classes.add("rate-limit")
        if 408 in statuses:
            self.legacy_categories.add("transport")
            self.failure_classes.add("timeout")
        if 409 in statuses:
            self.legacy_categories.add("transport")
            self.failure_classes.add("ambiguous")
        if any(term in lowered for term in ("model not found", "unknown model")) or 404 in statuses:
            self.legacy_categories.add("model")
            self.failure_classes.add("protocol")
        if any(status in statuses for status in (400, 405, 406, 410, 411, 412, 413, 414, 415, 416, 417, 418, 421, 422, 423, 424, 425, 426, 428, 431, 451)):
            self.legacy_categories.add("transport")
            self.failure_classes.add("protocol")
        if any(term in lowered for term in ("out of memory", "no space", "resource exhausted")):
            self.legacy_categories.add("resource")
        if any(term in lowered for term in ("malformed response", "invalid response", "invalid_response", "protocol error")):
            self.legacy_categories.add("transport")
            self.failure_classes.add("protocol")
        if any(500 <= status <= 599 for status in statuses):
            self.legacy_categories.add("transport")
            self.failure_classes.add("protocol")
        if any(term in lowered for term in ("connection refused", "connection reset", "connect failed", "disconnect", "network", "dns")):
            self.legacy_categories.add("transport")
            self.failure_classes.add("network")
            if not statuses:
                self.connection_state = "failed"
                self.response_header_state = "not-received"
        elif any(term in lowered for term in ("connect", "stream", "transport")):
            self.legacy_categories.add("transport")

    def finalize(
        self,
        *,
        exit_code: int | None,
        timed_out: bool,
        turn_completed: bool,
        turn_failed: bool,
        child_process_state: str,
        stdout_pipe_state: str,
        stderr_pipe_state: str,
    ) -> dict[str, Any]:
        if timed_out:
            failure_class = "timeout"
            exit_cause = "timeout"
        elif exit_code is None:
            failure_class = "child-process"
            exit_cause = "spawn-error"
        elif exit_code != 0:
            failure_class = self._classified_failure(default="child-process")
            exit_cause = "nonzero-exit" if self.line_count else "early-exit"
        elif not turn_completed:
            failure_class = self._classified_failure(default="ambiguous")
            exit_cause = "zero-without-terminal"
        elif turn_failed:
            failure_class = self._classified_failure(default="unknown")
            exit_cause = "completed"
        else:
            failure_class = "none"
            exit_cause = "completed"

        status_category = "none"
        if self.http_statuses:
            status_category = f"{self.http_statuses[-1] // 100}xx"
        provider_code = self.provider_codes[-1] if self.provider_codes else "none"
        provider_type = self.provider_types[-1] if self.provider_types else "none"
        legacy_priority = ("authentication", "model", "rate-limit", "resource", "transport")
        legacy_category = next((name for name in legacy_priority if name in self.legacy_categories), "process" if failure_class != "none" else "none")
        summary = (
            f"class={failure_class}; http={status_category}; code={provider_code}; "
            f"exit={exit_cause}; child={child_process_state}; "
            f"pipes={stdout_pipe_state}/{stderr_pipe_state}; "
            f"structured_errors={self.structured_error_count}"
        )
        return {
            "schema_version": SCHEMA_VERSION,
            "category": legacy_category,
            "failure_class": failure_class,
            "http_status_category": status_category,
            "provider_error_code": provider_code,
            "provider_error_type": provider_type,
            "connection_state": self.connection_state,
            "response_header_state": self.response_header_state,
            "subprocess_exit_cause": exit_cause,
            "child_process_state": child_process_state,
            "stdout_pipe_state": stdout_pipe_state,
            "stderr_pipe_state": stderr_pipe_state,
            "stderr_line_count": self.line_count,
            "stderr_sha256": self.digest.hexdigest(),
            "structured_error_count": self.structured_error_count,
            "structured_error_sources": sorted(self.structured_error_sources),
            "redacted_summary": summary,
        }

    def _classified_failure(self, *, default: str) -> str:
        for name in ("auth", "rate-limit", "timeout", "network", "protocol", "ambiguous"):
            if name in self.failure_classes:
                return name
        return default
