#!/usr/bin/env python3
"""Single-attempt, redacted probes for a configured Responses provider."""

from __future__ import annotations

import http.client
import hashlib
import json
import socket
import ssl
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlsplit

try:
    from .toml_compat import tomllib
except ImportError:
    from toml_compat import tomllib

try:
    import transport_diagnostics
except ModuleNotFoundError:  # pragma: no cover - package import path
    from teaching import transport_diagnostics


MODEL = "gpt-5.6-sol"
MAX_RESPONSE_BYTES = 1024 * 1024
ALLOWED_PROVIDER_TYPES = {
    "authentication_error",
    "bad_request",
    "bad_request_error",
    "invalid_request",
    "invalid_request_error",
    "permission_denied",
    "rate_limit_exceeded",
    "model_not_found",
    "server_error",
    "service_unavailable",
}
ALLOWED_REJECTION_PARAMETERS = {
    "input",
    "instructions",
    "model",
    "reasoning",
    "store",
    "stream",
    "tools",
}


class WireProbeError(RuntimeError):
    pass


def load_provider_route(codex_home: Path | str) -> dict[str, Any]:
    home = Path(codex_home)
    try:
        config = tomllib.loads((home / "config.toml").read_text(encoding="utf-8"))
    except (OSError, ValueError, tomllib.TOMLDecodeError) as exc:
        raise WireProbeError("provider configuration is missing or invalid") from exc
    provider_name = config.get("model_provider")
    providers = config.get("model_providers")
    provider = providers.get(provider_name) if isinstance(providers, dict) and isinstance(provider_name, str) else None
    if provider_name != "custom" or not isinstance(provider, dict):
        raise WireProbeError("a custom provider route is required")
    required = {"name", "base_url", "wire_api", "requires_openai_auth"}
    if not required.issubset(provider):
        raise WireProbeError("provider route is missing required semantic fields")
    if provider.get("wire_api") != "responses":
        raise WireProbeError("provider wire_api must be responses")
    if not isinstance(provider.get("requires_openai_auth"), bool):
        raise WireProbeError("requires_openai_auth must be boolean")
    base_url = provider.get("base_url")
    if not isinstance(base_url, str) or not base_url:
        raise WireProbeError("provider base_url must be a non-empty string")
    parsed = urlsplit(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise WireProbeError("provider base_url must be an HTTP(S) endpoint without user information")
    catalog_ref = config.get("model_catalog_json")
    if not isinstance(catalog_ref, str) or "\\" in catalog_ref:
        raise WireProbeError("model_catalog_json must be a relative POSIX path")
    catalog_path = PurePosixPath(catalog_ref)
    if catalog_path.is_absolute() or any(part in {"", ".", ".."} for part in catalog_path.parts):
        raise WireProbeError("model_catalog_json must stay within CODEX_HOME")
    return {
        "provider_name": provider_name,
        "base_url": base_url,
        "wire_api": provider["wire_api"],
        "requires_openai_auth": provider["requires_openai_auth"],
        "model": config.get("model", MODEL),
        "catalog_path": home.joinpath(*catalog_path.parts),
    }


def route_summary(route: dict[str, Any]) -> dict[str, Any]:
    return {
        "provider_kind": "custom",
        "wire_api": route.get("wire_api", "unknown"),
        "requires_openai_auth": route.get("requires_openai_auth", "unknown"),
        "required_fields_present": all(
            key in route for key in ("base_url", "provider_name", "requires_openai_auth", "wire_api")
        ),
        "endpoint_persisted": False,
    }


def _endpoint(route: dict[str, Any]) -> tuple[Any, str, int]:
    parsed = urlsplit(str(route["base_url"]))
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    base_path = parsed.path.rstrip("/")
    path = f"{base_path}/responses" if base_path else "/responses"
    if parsed.query:
        path = f"{path}?{parsed.query}"
    return parsed, path, port


def probe_network(route: dict[str, Any], *, timeout: float = 5.0) -> dict[str, Any]:
    parsed, _, port = _endpoint(route)
    result: dict[str, Any] = {
        "dns_state": "not-observed",
        "tcp_state": "not-observed",
        "tls_state": "not-observed" if parsed.scheme == "https" else "not-required",
        "connection_state": "unknown",
        "attempts": {"dns": 0, "tcp": 0, "tls": 0},
        "failure_class": "none",
        "endpoint_persisted": False,
    }
    connected: socket.socket | None = None
    try:
        result["attempts"]["dns"] = 1
        addresses = socket.getaddrinfo(parsed.hostname, port, type=socket.SOCK_STREAM)
        if not addresses:
            raise OSError("dns returned no address")
        result["dns_state"] = "resolved"
        family, socktype, proto, _, sockaddr = addresses[0]
        result["attempts"]["tcp"] = 1
        connected = socket.socket(family, socktype, proto)
        connected.settimeout(timeout)
        connected.connect(sockaddr)
        result["tcp_state"] = "connected"
        if parsed.scheme == "https":
            result["attempts"]["tls"] = 1
            context = ssl.create_default_context()
            connected = context.wrap_socket(connected, server_hostname=parsed.hostname)
            result["tls_state"] = "negotiated"
        result["connection_state"] = "established"
        result["status"] = "passed"
    except socket.gaierror:
        result.update({"status": "blocked", "dns_state": "failed", "failure_class": "network"})
    except ssl.SSLError:
        result.update({"status": "blocked", "tls_state": "failed", "failure_class": "protocol"})
    except (OSError, TimeoutError):
        if result["dns_state"] == "resolved" and result["tcp_state"] == "not-observed":
            result["tcp_state"] = "failed"
        result.update({"status": "blocked", "connection_state": "failed", "failure_class": "network"})
    finally:
        if connected is not None:
            try:
                connected.close()
            except OSError:
                pass
    return result


def _usage(value: Any) -> dict[str, int]:
    raw = value if isinstance(value, dict) else {}
    input_tokens = raw.get("input_tokens", 0)
    output_tokens = raw.get("output_tokens", 0)
    total_tokens = raw.get("total_tokens", input_tokens + output_tokens)
    return {
        "input_tokens": input_tokens if isinstance(input_tokens, int) and input_tokens >= 0 else 0,
        "output_tokens": output_tokens if isinstance(output_tokens, int) and output_tokens >= 0 else 0,
        "total_tokens": total_tokens if isinstance(total_tokens, int) and total_tokens >= 0 else 0,
    }


def _normalized_allowed(value: Any, allowed: set[str]) -> str:
    if not isinstance(value, str) or not value:
        return "none"
    normalized = value.lower().replace("-", "_").replace(".", "_")
    return normalized if normalized in allowed else "unrecognized"


def _rejection_projection(message: Any) -> dict[str, str]:
    """Project an in-memory provider message onto fixed, non-secret labels."""
    if not isinstance(message, str) or not message.strip():
        return {"rejection_class": "none", "parameter": "none"}

    normalized = message.casefold().replace("-", "_")
    words = set(normalized.replace(".", " ").replace(":", " ").split())
    parameter = next(
        (name for name in sorted(ALLOWED_REJECTION_PARAMETERS) if name in words),
        "none",
    )

    if any(term in normalized for term in ("authentication", "unauthorized", "api key", "api_key", "credential")):
        rejection_class = "auth"
    elif "model" in words and any(
        term in normalized for term in ("unknown", "unsupported", "not found", "not_found", "invalid")
    ):
        rejection_class = "model"
    elif "input" in words and any(
        term in normalized for term in ("array", "object", "string", "shape", "must be", "expected")
    ):
        rejection_class = "input-shape"
    elif parameter != "none" and any(
        term in normalized for term in ("parameter", "field", "argument", "unsupported", "unknown", "invalid")
    ):
        rejection_class = "parameter"
    elif any(term in normalized for term in ("route", "endpoint", "path")) and any(
        term in normalized for term in ("not found", "not_found", "unknown", "invalid", "unsupported")
    ):
        rejection_class = "path"
    elif any(
        term in normalized
        for term in ("malformed", "invalid json", "invalid_json", "parse error", "protocol", "payload")
    ):
        rejection_class = "protocol"
    else:
        rejection_class = "unknown"

    return {"rejection_class": rejection_class, "parameter": parameter}


def _error_shape(item: dict[str, Any]) -> dict[str, Any]:
    candidate = item.get("error")
    if not isinstance(candidate, dict):
        response = item.get("response")
        candidate = response.get("error") if isinstance(response, dict) else None
    if not isinstance(candidate, dict):
        return {
            "error_object_state": "not-observed",
            "error_type_state": "not-observed",
            "error_code_state": "not-observed",
            "provider_error_type": "none",
            "provider_error_code": "none",
            "rejection_class": "none",
            "parameter": "none",
        }
    error_type = candidate.get("type")
    error_code = candidate.get("code")
    projection = _rejection_projection(candidate.get("message"))
    return {
        "error_object_state": "observed",
        "error_type_state": "observed" if isinstance(error_type, str) and error_type else "not-observed",
        "error_code_state": "observed" if isinstance(error_code, str) and error_code else "not-observed",
        "provider_error_type": _normalized_allowed(error_type, ALLOWED_PROVIDER_TYPES),
        "provider_error_code": _normalized_allowed(error_code, set(transport_diagnostics.ALLOWED_PROVIDER_CODES)),
        **projection,
    }


def _wire_shape(
    route: dict[str, Any],
    *,
    authenticated: bool,
    responses_lite_header: bool,
    input_kind: str,
    profile: str,
) -> dict[str, Any]:
    return {
        "method": "POST",
        "endpoint_path_mode": "base-path-plus-responses",
        "body_fields": ["input", "model", "store", "stream"],
        "input_kind": input_kind,
        "profile": profile,
        "stream": True,
        "store": False,
        "content_type": "application/json",
        "accept": "text/event-stream",
        "authorization_header_present": authenticated,
        "responses_lite_header_present": responses_lite_header,
        "wire_api": route.get("wire_api", "unknown"),
    }


def _request_id_hash(response: http.client.HTTPResponse) -> str:
    value = response.headers.get("x-request-id") or response.headers.get("request-id")
    if not value:
        return "not-observed"
    return hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()


def probe_responses(
    route: dict[str, Any],
    *,
    api_key: str | None,
    timeout: float = 30.0,
    responses_lite_header: bool = False,
    input_kind: str = "string",
    request_profile: str = "baseline",
) -> dict[str, Any]:
    if route.get("requires_openai_auth") and not api_key:
        raise WireProbeError("an in-memory API key is required by this provider route")
    parsed, path, port = _endpoint(route)
    reducer = transport_diagnostics.TransportDiagnosticReducer()
    if request_profile == "baseline":
        if input_kind == "string":
            request_input: Any = "Reply with WIRE_OK."
        elif input_kind == "message-array":
            request_input = [
                {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": "Reply with WIRE_OK."}],
                }
            ]
        else:
            raise WireProbeError("input_kind must be string or message-array")
        payload: dict[str, Any] = {
            "model": route.get("model", MODEL),
            "input": request_input,
            "stream": True,
            "store": False,
        }
        effective_input_kind = input_kind
        effective_lite_header = responses_lite_header
    elif request_profile == "codex-lite-minimal":
        payload = {
            "model": route.get("model", MODEL),
            "input": [
                {"type": "additional_tools", "role": "developer", "tools": []},
                {
                    "type": "message",
                    "role": "developer",
                    "content": [{"type": "input_text", "text": "Reply with WIRE_OK."}],
                },
                {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": "Reply with WIRE_OK."}],
                },
            ],
            "tool_choice": "auto",
            "parallel_tool_calls": False,
            "reasoning": {"effort": "low", "context": "all_turns"},
            "store": False,
            "stream": True,
            "include": ["reasoning.encrypted_content"],
            "text": {"verbosity": "low"},
        }
        effective_input_kind = "codex-message-array"
        effective_lite_header = True
    else:
        raise WireProbeError("request_profile must be baseline or codex-lite-minimal")
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    headers = {"Content-Type": "application/json", "Accept": "text/event-stream"}
    if effective_lite_header:
        headers["x-openai-internal-codex-responses-lite"] = "true"
    if route.get("requires_openai_auth"):
        headers["Authorization"] = f"Bearer {api_key}"
    event_types: set[str] = set()
    terminal = False
    usage = _usage({})
    output_observed = False
    status_code: int | None = None
    error_shape = _error_shape({})
    event_shape: set[str] = set()
    request_id_hash = "not-observed"
    authenticated = bool(route.get("requires_openai_auth"))
    connection: http.client.HTTPConnection | None = None
    try:
        connection_type = http.client.HTTPSConnection if parsed.scheme == "https" else http.client.HTTPConnection
        connection = connection_type(parsed.hostname, port, timeout=timeout)
        connection.request("POST", path, body=body, headers=headers)
        response = connection.getresponse()
        status_code = response.status
        request_id_hash = _request_id_hash(response)
        reducer.consume(f"HTTP {status_code}")
        raw = response.read(MAX_RESPONSE_BYTES + 1)
        if len(raw) > MAX_RESPONSE_BYTES:
            reducer.consume_structured_error("protocol response exceeded bounded size", "error")
            raw = raw[:MAX_RESPONSE_BYTES]
        text = raw.decode("utf-8", errors="replace")
        objects: list[dict[str, Any]] = []
        for line in text.splitlines():
            value = line[5:].strip() if line.startswith("data:") else line.strip()
            if not value or value == "[DONE]":
                continue
            try:
                parsed_value = json.loads(value)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed_value, dict):
                objects.append(parsed_value)
        if not objects:
            try:
                value = json.loads(text)
            except json.JSONDecodeError:
                value = None
            if isinstance(value, dict):
                objects.append(value)
        for item in objects:
            event_type = item.get("type") if isinstance(item.get("type"), str) else "response"
            event_types.add(event_type)
            event_shape.add(event_type)
            observed_error = _error_shape(item)
            if observed_error["error_object_state"] == "observed":
                error_shape = observed_error
            response_value = item.get("response") if isinstance(item.get("response"), dict) else item
            if event_type == "response.completed" or response_value.get("status") == "completed":
                terminal = True
            if event_type == "response.failed" or response_value.get("status") == "failed":
                error = response_value.get("error")
                message = error.get("message") if isinstance(error, dict) else str(error or "response failed")
                reducer.consume_structured_error(message, "response.failed")
            candidate_usage = response_value.get("usage")
            if isinstance(candidate_usage, dict):
                usage = _usage(candidate_usage)
            output = response_value.get("output")
            output_observed = output_observed or bool(output)
        if status_code is not None and not 200 <= status_code <= 299:
            reducer.consume_structured_error(text, "response.failed")
        success = status_code is not None and 200 <= status_code <= 299 and terminal and usage["total_tokens"] > 0
        diagnostic = reducer.finalize(
            exit_code=0 if success else 1,
            timed_out=False,
            turn_completed=success,
            turn_failed=not success,
            child_process_state="not-applicable",
            stdout_pipe_state="not-applicable",
            stderr_pipe_state="not-applicable",
        )
        return {
            "status": "passed" if success else "blocked",
            "http_status": status_code if status_code is not None else 0,
            "http_status_category": diagnostic["http_status_category"],
            "response_header_state": diagnostic["response_header_state"],
            "connection_state": diagnostic["connection_state"],
            "terminal_event_observed": terminal,
            "event_types": sorted(event_types),
            "event_shape": {"types": sorted(event_shape), "count": len(objects)},
            "error_shape": error_shape,
            "request_id_sha256": request_id_hash,
            "request_shape": _wire_shape(
                route,
                authenticated=authenticated,
                responses_lite_header=effective_lite_header,
                input_kind=effective_input_kind,
                profile=request_profile,
            ),
            "codex_wire_comparison": {
                "status": "probe-contract-only",
                "unverified_until_cli_canary": True,
            },
            "usage": usage,
            "output_observed": output_observed,
            "diagnostic": diagnostic,
            "request_count": 1,
            "automatic_retry_observed": False,
            "raw_response_persisted": False,
            "endpoint_persisted": False,
            "prompt_persisted": False,
        }
    except (OSError, TimeoutError, http.client.HTTPException):
        reducer.consume_structured_error("network connection failed", "error")
        diagnostic = reducer.finalize(
            exit_code=1,
            timed_out=False,
            turn_completed=False,
            turn_failed=True,
            child_process_state="not-applicable",
            stdout_pipe_state="not-applicable",
            stderr_pipe_state="not-applicable",
        )
        return {
            "status": "blocked",
            "http_status": 0,
            "http_status_category": "none",
            "response_header_state": "not-received",
            "connection_state": "failed",
            "terminal_event_observed": False,
            "event_types": [],
            "event_shape": {"types": [], "count": 0},
            "error_shape": error_shape,
            "request_id_sha256": request_id_hash,
            "request_shape": _wire_shape(
                route,
                authenticated=authenticated,
                responses_lite_header=effective_lite_header,
                input_kind=effective_input_kind,
                profile=request_profile,
            ),
            "codex_wire_comparison": {
                "status": "probe-contract-only",
                "unverified_until_cli_canary": True,
            },
            "usage": _usage({}),
            "output_observed": False,
            "diagnostic": diagnostic,
            "request_count": 1,
            "automatic_retry_observed": False,
            "raw_response_persisted": False,
            "endpoint_persisted": False,
            "prompt_persisted": False,
        }
    finally:
        if connection is not None:
            connection.close()
