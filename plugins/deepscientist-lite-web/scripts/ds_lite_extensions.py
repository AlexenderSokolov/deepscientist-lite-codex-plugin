#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Callable
from urllib.parse import quote, urljoin, urlsplit, urlunsplit


CAPABILITY_SCHEMA = "ds-lite.capability.v1"
SOURCE_RECORD_SCHEMA = "ds-lite.source-record.v1"
SOURCE_RECORD_V2_SCHEMA = "ds-lite.source-record.v2"
CORE_NAME = "deepscientist-lite"
CORE_VERSION = "0.9.0-beta.1"
ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
SHA256_RE = re.compile(r"^[a-f0-9]{64}$")
EXTERNAL_RE = re.compile(r"^external://([a-z][a-z0-9_-]*)/(.+)$")
CAPABILITIES = {"search", "fetch", "render", "interact"}
AUTHENTICATION = {"none", "api-key", "user-session", "not-observed"}
STORAGE_BOUNDARIES = {"project", "external", "remote", "none", "not-observed"}
AVAILABILITY = {"available", "unavailable", "needs-config", "not-observed"}
SOURCE_STATUSES = {"captured", "partial", "failed", "not-observed"}
FAILURE_LAYERS = {
    "none",
    "authorization",
    "configuration",
    "dns",
    "network",
    "http",
    "render",
    "parse",
    "storage",
    "policy",
    "unknown",
}


def _emit_json(payload: Any) -> None:
    """Keep CLI receipts readable by both UTF-8 and legacy Windows consoles."""
    print(json.dumps(payload, ensure_ascii=True))
SENSITIVE_KEYS = {
    "authorization",
    "cookie",
    "cookies",
    "credential",
    "credentials",
    "api_key",
    "apikey",
    "password",
    "secret",
    "token",
    "private_key",
    "chain_of_thought",
    "reasoning_trace",
    "hidden_reasoning",
}

CAPABILITY_REQUIRED = {
    "schema_version",
    "backend_id",
    "backend_version",
    "capabilities",
    "authentication",
    "storage_boundary",
    "availability",
    "observed_at",
    "extensions",
}
SOURCE_REQUIRED = {
    "schema_version",
    "source_id",
    "source_uri",
    "retrieved_at",
    "content_sha256",
    "media_type",
    "backend_id",
    "transformations",
    "artifact_refs",
    "status",
    "failure_layer",
    "unverified_items",
    "policy",
    "extensions",
}
SOURCE_V2_REQUIRED = SOURCE_REQUIRED | {"failure_reason", "budget"}
OPENCLI_BACKEND_ID = "opencli-cli"
OPENCLI_FORBIDDEN = {
    "auth", "profile", "bind", "click", "fill", "select", "upload", "cookie", "cookies",
}


class ExtensionProtocolError(ValueError):
    pass


def _normalized_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value).lower()).strip("_")


def _find_sensitive(value: Any, prefix: str = "") -> str | None:
    if isinstance(value, dict):
        for key, item in value.items():
            location = f"{prefix}.{key}" if prefix else str(key)
            normalized = _normalized_key(key)
            if normalized in SENSITIVE_KEYS or any(
                normalized.endswith(suffix)
                for suffix in ("_token", "_secret", "_password", "_api_key", "_credential")
            ):
                return location
            found = _find_sensitive(item, location)
            if found:
                return found
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found = _find_sensitive(item, f"{prefix}[{index}]")
            if found:
                return found
    return None


def _require_object(payload: Any, schema: str, required: set[str]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ExtensionProtocolError(f"{schema} must contain a JSON object")
    missing = required - set(payload)
    unknown = set(payload) - required
    if missing:
        raise ExtensionProtocolError(f"{schema} missing fields: {', '.join(sorted(missing))}")
    if unknown:
        raise ExtensionProtocolError(f"{schema} has unsupported fields: {', '.join(sorted(unknown))}")
    if payload.get("schema_version") != schema:
        raise ExtensionProtocolError(f"schema_version must be {schema}")
    sensitive = _find_sensitive(payload)
    if sensitive:
        raise ExtensionProtocolError(f"{schema} contains a sensitive field: {sensitive}")
    if not isinstance(payload.get("extensions"), dict):
        raise ExtensionProtocolError("extensions must be an object")
    return payload


def _validate_id(value: Any, label: str) -> str:
    if not isinstance(value, str) or not ID_RE.fullmatch(value):
        raise ExtensionProtocolError(f"{label} must match [a-z0-9][a-z0-9._-]{{0,127}}")
    return value


def _validate_timestamp(value: Any, label: str) -> str:
    if not isinstance(value, str):
        raise ExtensionProtocolError(f"{label} must be an ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ExtensionProtocolError(f"{label} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise ExtensionProtocolError(f"{label} must include a timezone")
    return parsed.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _validate_ref(value: Any, label: str, *, allow_empty: bool = False) -> str:
    if allow_empty and value == "":
        return ""
    if not isinstance(value, str) or not value.strip():
        raise ExtensionProtocolError(f"{label} must be a non-empty relative or external path")
    raw = value.strip().replace("\\", "/")
    external = EXTERNAL_RE.fullmatch(raw)
    if external:
        raw_path = external.group(2)
    else:
        if Path(raw).expanduser().is_absolute() or PureWindowsPath(raw).is_absolute():
            raise ExtensionProtocolError(f"{label} forbids absolute paths")
        raw_path = raw
    path = PurePosixPath(raw_path)
    if path.is_absolute() or not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        raise ExtensionProtocolError(f"{label} must be normalized without '..'")
    return raw


def _validate_refs(value: Any, label: str, *, allow_empty: bool = False) -> list[str]:
    if not isinstance(value, list) or (not allow_empty and not value):
        raise ExtensionProtocolError(f"{label} must be a non-empty list")
    refs = [_validate_ref(item, f"{label}[{index}]") for index, item in enumerate(value)]
    if len(refs) != len(set(refs)):
        raise ExtensionProtocolError(f"{label} contains duplicates")
    return refs


def _validate_public_uri(value: Any) -> str:
    if not isinstance(value, str):
        raise ExtensionProtocolError("source_uri must be an http or https URI")
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise ExtensionProtocolError("source_uri must be a public http or https URI without credentials")
    hostname = parsed.hostname.lower().rstrip(".")
    if hostname == "localhost" or hostname.endswith(".localhost") or hostname.endswith(".local"):
        raise ExtensionProtocolError("source_uri must not target a local host")
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        address = None
    if address and (not address.is_global):
        raise ExtensionProtocolError("source_uri must target a public address")
    return value


def _validate_domain_scope(value: str, allowed_domains: list[str]) -> None:
    if not allowed_domains:
        raise ExtensionProtocolError("at least one allowed domain is required")
    hostname = (urlsplit(value).hostname or "").lower().rstrip(".")
    normalized = [item.lower().strip().lstrip(".").rstrip(".") for item in allowed_domains if item.strip()]
    if not normalized or not any(hostname == item or hostname.endswith("." + item) for item in normalized):
        raise ExtensionProtocolError("URL is outside the allowed domain scope")


def _validate_run_scope(value: str, args: argparse.Namespace) -> None:
    """Require an explicit non-empty domain allowlist before any network call."""
    _validate_domain_scope(value, getattr(args, "allowed_domains", []))


def _transport_url(value: str) -> str:
    """Encode a validated public URL for urllib without changing its scope semantics."""
    parsed = urlsplit(value)
    hostname = parsed.hostname or ""
    try:
        host = hostname.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise ExtensionProtocolError("source_uri hostname cannot be IDNA encoded") from exc
    netloc = host if parsed.port is None else f"{host}:{parsed.port}"
    return urlunsplit((
        parsed.scheme,
        netloc,
        quote(parsed.path, safe="/%:@"),
        quote(parsed.query, safe="=&/%:@?"),
        "",
    ))


def validate_capability(payload: Any) -> dict[str, Any]:
    payload = _require_object(payload, CAPABILITY_SCHEMA, CAPABILITY_REQUIRED)
    _validate_id(payload["backend_id"], "backend_id")
    if not isinstance(payload["backend_version"], str) or not payload["backend_version"].strip():
        raise ExtensionProtocolError("backend_version must be a non-empty string")
    capabilities = payload["capabilities"]
    if not isinstance(capabilities, list) or not capabilities or not all(item in CAPABILITIES for item in capabilities):
        raise ExtensionProtocolError("capabilities must contain search, fetch, render, or interact")
    if len(capabilities) != len(set(capabilities)):
        raise ExtensionProtocolError("capabilities contains duplicates")
    if payload["authentication"] not in AUTHENTICATION:
        raise ExtensionProtocolError("authentication is invalid")
    if payload["storage_boundary"] not in STORAGE_BOUNDARIES:
        raise ExtensionProtocolError("storage_boundary is invalid")
    if payload["availability"] not in AVAILABILITY:
        raise ExtensionProtocolError("availability is invalid")
    _validate_timestamp(payload["observed_at"], "observed_at")
    return json.loads(json.dumps(payload))


def validate_source_record(payload: Any) -> dict[str, Any]:
    payload = _require_object(payload, SOURCE_RECORD_SCHEMA, SOURCE_REQUIRED)
    _validate_id(payload["source_id"], "source_id")
    _validate_public_uri(payload["source_uri"])
    _validate_timestamp(payload["retrieved_at"], "retrieved_at")
    if not isinstance(payload["content_sha256"], str) or not SHA256_RE.fullmatch(payload["content_sha256"]):
        raise ExtensionProtocolError("content_sha256 must contain 64 lowercase hex characters")
    if not isinstance(payload["media_type"], str) or "/" not in payload["media_type"]:
        raise ExtensionProtocolError("media_type must be a MIME type")
    _validate_id(payload["backend_id"], "backend_id")
    transformations = payload["transformations"]
    if not isinstance(transformations, list) or not all(isinstance(item, str) and item for item in transformations):
        raise ExtensionProtocolError("transformations must be a list of strings")
    _validate_refs(payload["artifact_refs"], "artifact_refs")
    if payload["status"] not in SOURCE_STATUSES:
        raise ExtensionProtocolError("status is invalid")
    if payload["failure_layer"] not in FAILURE_LAYERS:
        raise ExtensionProtocolError("failure_layer is invalid")
    if not isinstance(payload["unverified_items"], list) or not all(
        isinstance(item, str) for item in payload["unverified_items"]
    ):
        raise ExtensionProtocolError("unverified_items must be a list of strings")
    policy = payload["policy"]
    expected_policy = {"public_only", "authenticated", "submitted_forms", "cookies_persisted"}
    if not isinstance(policy, dict) or set(policy) != expected_policy:
        raise ExtensionProtocolError("policy must contain the four public-only controls")
    if policy != {
        "public_only": True,
        "authenticated": False,
        "submitted_forms": False,
        "cookies_persisted": False,
    }:
        raise ExtensionProtocolError("source records in v1 must remain public-only")
    return json.loads(json.dumps(payload))


def validate_source_record_v2(payload: Any) -> dict[str, Any]:
    """Validate the write-side v2 envelope while accepting v1 on read paths."""
    payload = _require_object(payload, SOURCE_RECORD_V2_SCHEMA, SOURCE_V2_REQUIRED)
    _validate_id(payload["source_id"], "source_id")
    _validate_public_uri(payload["source_uri"])
    _validate_timestamp(payload["retrieved_at"], "retrieved_at")
    if payload["status"] in {"captured", "partial"}:
        if not isinstance(payload["content_sha256"], str) or not SHA256_RE.fullmatch(payload["content_sha256"]):
            raise ExtensionProtocolError("captured sources require content_sha256")
        _validate_refs(payload["artifact_refs"], "artifact_refs")
    elif payload["status"] in {"failed", "not-observed"}:
        if payload["content_sha256"] not in {"", None}:
            raise ExtensionProtocolError("failed sources must not claim a content hash")
        if payload["artifact_refs"] not in ([], None):
            raise ExtensionProtocolError("failed sources must not claim artifacts")
    else:
        raise ExtensionProtocolError("status is invalid")
    if not isinstance(payload["media_type"], str) or (payload["status"] in {"captured", "partial"} and "/" not in payload["media_type"]):
        raise ExtensionProtocolError("media_type is invalid")
    _validate_id(payload["backend_id"], "backend_id")
    if not isinstance(payload["transformations"], list) or not all(isinstance(item, str) and item for item in payload["transformations"]):
        raise ExtensionProtocolError("transformations must be a list of strings")
    if payload["failure_layer"] not in FAILURE_LAYERS:
        raise ExtensionProtocolError("failure_layer is invalid")
    if payload["status"] in {"failed", "not-observed"} and payload["failure_layer"] == "none":
        raise ExtensionProtocolError("failed sources require a failure layer")
    if not isinstance(payload["unverified_items"], list) or not all(isinstance(item, str) for item in payload["unverified_items"]):
        raise ExtensionProtocolError("unverified_items must be a list of strings")
    if not isinstance(payload["failure_reason"], str):
        raise ExtensionProtocolError("failure_reason must be a string")
    if not isinstance(payload["budget"], dict) or any(not isinstance(value, (int, float)) or value < 0 for value in payload["budget"].values()):
        raise ExtensionProtocolError("budget must be a non-negative numeric object")
    policy = payload["policy"]
    if policy != {"public_only": True, "authenticated": False, "submitted_forms": False, "cookies_persisted": False}:
        raise ExtensionProtocolError("source records in v2 must remain public-only")
    return json.loads(json.dumps(payload))


def doctor(core_root: str | None) -> tuple[dict[str, Any], int]:
    raw = core_root or os.environ.get("DS_LITE_CORE_ROOT", "").strip()
    if not raw:
        return {
            "schema_version": "ds-lite.pack-doctor.v1",
            "status": "blocked",
            "reason": "core-root-not-provided",
            "required_plugin": CORE_NAME,
            "required_version": CORE_VERSION,
        }, 2
    manifest_path = Path(raw).expanduser() / ".codex-plugin" / "plugin.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {
            "schema_version": "ds-lite.pack-doctor.v1",
            "status": "blocked",
            "reason": "core-manifest-unavailable",
            "required_plugin": CORE_NAME,
            "required_version": CORE_VERSION,
        }, 2
    observed = {"plugin": manifest.get("name"), "version": manifest.get("version")}
    if observed != {"plugin": CORE_NAME, "version": CORE_VERSION}:
        return {
            "schema_version": "ds-lite.pack-doctor.v1",
            "status": "blocked",
            "reason": "incompatible-core",
            "required_plugin": CORE_NAME,
            "required_version": CORE_VERSION,
            "observed": observed,
        }, 2
    return {
        "schema_version": "ds-lite.pack-doctor.v1",
        "status": "passed",
        "required_plugin": CORE_NAME,
        "required_version": CORE_VERSION,
        "observed": observed,
    }, 0


def _path_within(path: Path, root: Path) -> Path:
    resolved = path.expanduser().resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ExtensionProtocolError("artifact and output paths must remain inside the project root") from exc
    return resolved


def _project_path(raw: str | Path, root: Path) -> Path:
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = root / path
    return _path_within(path, root)


def record_source(args: argparse.Namespace) -> dict[str, Any]:
    project_root = Path(args.project_root).expanduser().resolve()
    if not project_root.is_dir():
        raise ExtensionProtocolError("project-root must be an existing directory")
    artifact = _project_path(args.artifact, project_root)
    output = _project_path(args.output, project_root)
    package_root = Path(__file__).resolve().parents[1]
    if package_root == output or package_root in output.parents:
        raise ExtensionProtocolError("source records must not be written inside the installed plugin")
    if not artifact.is_file():
        raise ExtensionProtocolError("artifact must be an existing file")
    if output.exists():
        raise ExtensionProtocolError("output already exists; refusing overwrite")
    relative_artifact = artifact.relative_to(project_root).as_posix()
    payload = {
        "schema_version": SOURCE_RECORD_SCHEMA,
        "source_id": args.source_id,
        "source_uri": args.source_uri,
        "retrieved_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "content_sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
        "media_type": args.media_type,
        "backend_id": args.backend_id,
        "transformations": args.transformation or ["capture"],
        "artifact_refs": [relative_artifact],
        "status": "captured",
        "failure_layer": "none",
        "unverified_items": args.unverified_item or [],
        "policy": {
            "public_only": True,
            "authenticated": False,
            "submitted_forms": False,
            "cookies_persisted": False,
        },
        "extensions": {},
    }
    validate_source_record(payload)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def record_source_v2(args: argparse.Namespace) -> dict[str, Any]:
    """Write a v2 captured record; callers use failed records for diagnostics."""
    project_root = Path(args.project_root).expanduser().resolve()
    artifact = _project_path(args.artifact, project_root)
    output = _project_path(args.output, project_root)
    if not artifact.is_file() or output.exists():
        raise ExtensionProtocolError("v2 capture requires a new output and an existing artifact")
    payload = {
        "schema_version": SOURCE_RECORD_V2_SCHEMA,
        "source_id": args.source_id,
        "source_uri": args.source_uri,
        "retrieved_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "content_sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
        "media_type": args.media_type,
        "backend_id": args.backend_id,
        "transformations": args.transformation or ["capture"],
        "artifact_refs": [artifact.relative_to(project_root).as_posix()],
        "status": "captured",
        "failure_layer": "none",
        "unverified_items": args.unverified_item or [],
        "policy": {"public_only": True, "authenticated": False, "submitted_forms": False, "cookies_persisted": False},
        "failure_reason": "",
        "budget": {"pages": 1, "bytes": artifact.stat().st_size, "seconds": 0},
        "extensions": {},
    }
    validate_source_record_v2(payload)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def _bounded_fetch(
    url: str,
    *,
    timeout: float,
    max_bytes: int,
    allowed_domains: list[str] | None = None,
) -> tuple[str, bytes, str]:
    _validate_public_uri(url)
    if allowed_domains is not None:
        _validate_domain_scope(url, allowed_domains)
    request = urllib.request.Request(_transport_url(url), headers={"User-Agent": "ds-lite-web/0.2"}, method="GET")
    started = time.monotonic()
    class PublicRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            redirected = urljoin(req.full_url, newurl)
            _validate_public_uri(redirected)
            if allowed_domains is not None:
                _validate_domain_scope(redirected, allowed_domains)
            return super().redirect_request(req, fp, code, msg, headers, _transport_url(redirected))

    opener = urllib.request.build_opener(PublicRedirect)
    with opener.open(request, timeout=timeout) as response:
        final_url = response.geturl()
        _validate_public_uri(final_url)
        content = response.read(max_bytes + 1)
        if len(content) > max_bytes:
            raise ExtensionProtocolError("byte budget exceeded")
        if time.monotonic() - started > timeout:
            raise ExtensionProtocolError("time budget exceeded")
        return final_url, content, response.headers.get_content_type()


def _write_captured_v2(args: argparse.Namespace, content: bytes, media_type: str, final_url: str) -> dict[str, Any]:
    project_root = Path(args.project_root).expanduser().resolve()
    artifact = _project_path(args.output, project_root)
    record = _project_path(args.record_output, project_root)
    if artifact.exists() or record.exists():
        raise ExtensionProtocolError("fetch refuses to overwrite existing outputs")
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_bytes(content)
    payload = {
        "schema_version": SOURCE_RECORD_V2_SCHEMA,
        "source_id": args.source_id,
        "source_uri": final_url,
        "retrieved_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "content_sha256": hashlib.sha256(content).hexdigest(),
        "media_type": media_type,
        "backend_id": args.backend_id,
        "transformations": ["http-get"],
        "artifact_refs": [artifact.relative_to(project_root).as_posix()],
        "status": "captured",
        "failure_layer": "none",
        "unverified_items": [],
        "policy": {"public_only": True, "authenticated": False, "submitted_forms": False, "cookies_persisted": False},
        "failure_reason": "",
        "budget": {"pages": 1, "bytes": len(content), "seconds": args.timeout},
        "extensions": {"requested_uri": args.url},
    }
    validate_source_record_v2(payload)
    record.parent.mkdir(parents=True, exist_ok=True)
    record.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def _write_failed_v2(args: argparse.Namespace, *, backend_id: str, failure_layer: str, reason: str) -> None:
    """Preserve a diagnosable source record when a public capture never materializes."""
    project_root = Path(args.project_root).expanduser().resolve()
    record_path = _project_path(args.record_output, project_root)
    artifact_path = _project_path(args.output, project_root)
    if record_path.exists() or artifact_path.exists():
        return
    failed = {
        "schema_version": SOURCE_RECORD_V2_SCHEMA,
        "source_id": args.source_id,
        "source_uri": args.url,
        "retrieved_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "content_sha256": "",
        "media_type": "application/octet-stream",
        "backend_id": backend_id,
        "transformations": [],
        "artifact_refs": [],
        "status": "failed",
        "failure_layer": failure_layer,
        "unverified_items": ["content was not captured"],
        "policy": {"public_only": True, "authenticated": False, "submitted_forms": False, "cookies_persisted": False},
        "failure_reason": reason[:500],
        "budget": {"pages": 1, "bytes": args.max_bytes, "seconds": args.timeout},
        "extensions": {"requested_uri": args.url},
    }
    validate_source_record_v2(failed)
    record_path.parent.mkdir(parents=True, exist_ok=True)
    record_path.write_text(json.dumps(failed, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def fetch_public(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    try:
        _validate_run_scope(args.url, args)
        final_url, content, media_type = _bounded_fetch(
            args.url,
            timeout=args.timeout,
            max_bytes=args.max_bytes,
            allowed_domains=args.allowed_domains,
        )
        payload = _write_captured_v2(args, content, media_type, final_url)
        return {"status": "passed", "backend": args.backend_id, "source_record": payload}, 0
    except (OSError, urllib.error.URLError, ValueError, ExtensionProtocolError) as exc:
        failure_layer = "http" if isinstance(exc, urllib.error.HTTPError) else (
            "network" if isinstance(exc, (OSError, urllib.error.URLError)) else "policy"
        )
        try:
            _write_failed_v2(args, backend_id=args.backend_id, failure_layer=failure_layer, reason=str(exc))
        except (OSError, UnicodeError, ValueError, ExtensionProtocolError):
            pass
        return {
            "status": "blocked",
            "schema_version": SOURCE_RECORD_V2_SCHEMA,
            "source_uri": args.url,
            "failure_layer": failure_layer,
            "reason": str(exc),
        }, 2


def render_playwright(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    project_root = Path(args.project_root).expanduser().resolve()
    try:
        _validate_run_scope(args.url, args)
        artifact = _project_path(args.output, project_root)
        record = _project_path(args.record_output, project_root)
        if artifact.exists() or record.exists():
            raise ExtensionProtocolError("playwright refuses to overwrite existing outputs")
        runner = Path(__file__).with_name("ds_lite_playwright_render.mjs")
        completed = subprocess.run(
            [args.node_bin, str(runner), "--url", args.url, "--timeout", str(args.timeout), "--playwright-module", args.playwright_module],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=args.timeout + 5, check=False,
        )
        if completed.returncode != 0:
            try:
                failure = json.loads(completed.stdout)
                category = str(failure.get("error_category", "render"))
            except (TypeError, ValueError, json.JSONDecodeError):
                category = "render"
            if category not in {"timeout", "network", "render"}:
                category = "render"
            raise ExtensionProtocolError(f"playwright {category} failure")
        payload = json.loads(completed.stdout)
        final_url, text = str(payload["final_url"]), str(payload["text"])
        _validate_public_uri(final_url); _validate_domain_scope(final_url, args.allowed_domains)
        content = text.encode("utf-8")
        if len(content) > args.max_bytes:
            raise ExtensionProtocolError("playwright output exceeded byte budget")
        artifact.parent.mkdir(parents=True, exist_ok=True); artifact.write_bytes(content)
        source = {
            "schema_version": SOURCE_RECORD_V2_SCHEMA, "source_id": args.source_id, "source_uri": final_url,
            "retrieved_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"), "content_sha256": hashlib.sha256(content).hexdigest(),
            "media_type": "text/plain", "backend_id": "playwright-cli", "transformations": ["playwright-render"],
            "artifact_refs": [artifact.relative_to(project_root).as_posix()], "status": "captured", "failure_layer": "none", "unverified_items": [],
            "policy": {"public_only": True, "authenticated": False, "submitted_forms": False, "cookies_persisted": False}, "failure_reason": "",
            "budget": {"pages": 1, "bytes": len(content), "seconds": args.timeout}, "extensions": {"title": str(payload.get("title", ""))},
        }
        validate_source_record_v2(source); record.parent.mkdir(parents=True, exist_ok=True); record.write_text(json.dumps(source, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return {"status": "passed", "backend": "playwright-cli", "source_record": source}, 0
    except (OSError, ValueError, KeyError, json.JSONDecodeError, subprocess.TimeoutExpired, ExtensionProtocolError) as exc:
        try:
            _write_failed_v2(args, backend_id="playwright-cli", failure_layer="render", reason=str(exc))
        except (OSError, UnicodeError, ValueError, ExtensionProtocolError):
            pass
        return {"status": "blocked", "backend": "playwright-cli", "failure_layer": "render", "reason": str(exc)[:500]}, 2


def backend_doctor(playwright_module: str | None = None) -> dict[str, Any]:
    isolated_playwright = bool(playwright_module and Path(playwright_module).expanduser().is_dir())
    return {
        "schema_version": CAPABILITY_SCHEMA,
        "backends": [
            {"backend_id": "stdlib-http", "available": True, "capabilities": ["fetch"]},
            {"backend_id": "playwright-cli", "available": bool(shutil.which("playwright")) or isolated_playwright, "capabilities": ["render", "interact"], "isolated_runtime": isolated_playwright},
            {"backend_id": "firecrawl", "available": bool(os.environ.get("FIRECRAWL_API_KEY")), "capabilities": ["search", "fetch"]},
            {"backend_id": "agent-browser", "available": bool(shutil.which("agent-browser")), "capabilities": ["render", "interact"]},
            {"backend_id": OPENCLI_BACKEND_ID, "available": bool(shutil.which("opencli")), "capabilities": ["search", "fetch"]},
        ],
        "policy": {"public_only": True, "login": False, "cookies": False, "forms": False},
    }


def _opencli_manifest_path() -> Path | None:
    executable = shutil.which("opencli")
    if not executable:
        return None
    for parent in (Path(executable).resolve().parent, *Path(executable).resolve().parents):
        candidate = parent / "node_modules" / "@jackwener" / "opencli" / "cli-manifest.json"
        if candidate.is_file():
            return candidate
    return None


def _opencli_public_command(site: str, command: str) -> dict[str, Any]:
    manifest_path = _opencli_manifest_path()
    if manifest_path is None:
        raise ExtensionProtocolError("opencli executable or manifest is unavailable")
    try:
        entries = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ExtensionProtocolError("opencli manifest is unreadable") from exc
    matches = [item for item in entries if isinstance(item, dict) and item.get("site") == site and item.get("name") == command]
    if len(matches) != 1:
        raise ExtensionProtocolError("opencli command is not uniquely declared")
    entry = matches[0]
    if entry.get("access") != "read" or str(entry.get("strategy", "")).lower() != "public" or entry.get("browser") is not False:
        raise ExtensionProtocolError("opencli command is not a public read-only adapter")
    metadata = " ".join(str(entry.get(key, "")) for key in ("site", "name", "description", "modulePath", "sourceFile")).lower()
    if any(re.search(rf"\b{re.escape(token)}\b", metadata) for token in OPENCLI_FORBIDDEN):
        raise ExtensionProtocolError("opencli command declaration contains a forbidden capability")
    return entry


def _opencli(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    project_root = Path(args.project_root).expanduser().resolve()
    try:
        output_path = Path(args.output)
        record_path = Path(args.record_output)
        if not output_path.is_absolute():
            output_path = project_root / output_path
        if not record_path.is_absolute():
            record_path = project_root / record_path
        artifact = _project_path(output_path, project_root)
        record = _project_path(record_path, project_root)
        _validate_run_scope(args.url, args)
        entry = _opencli_public_command(args.site, args.opencli_command)
        executable = shutil.which("opencli")
        if not executable:
            raise ExtensionProtocolError("opencli executable is unavailable")
        if artifact.exists() or record.exists():
            raise ExtensionProtocolError("opencli refuses to overwrite existing outputs")
        command = [executable, args.site, args.opencli_command, *args.opencli_arg, "--format", "json"]
        env = os.environ.copy()
        for key in ("OPENCLI_PROFILE", "OPENCLI_CDP_ENDPOINT", "OPENCLI_WINDOW"):
            env.pop(key, None)
        started = time.monotonic()
        completed = subprocess.run(command, cwd=str(project_root), env=env, capture_output=True,
                                   text=True, encoding="utf-8", errors="replace",
                                   timeout=args.timeout, check=False)
        if completed.returncode != 0:
            raise ExtensionProtocolError(f"opencli returned exit code {completed.returncode}")
        raw = completed.stdout.encode("utf-8")
        if len(raw) > args.max_bytes:
            raise ExtensionProtocolError("opencli output exceeded byte budget")
        try:
            decoded = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise ExtensionProtocolError("opencli did not return JSON") from exc
        artifact.parent.mkdir(parents=True, exist_ok=True)
        artifact.write_bytes(raw)
        source = {
            "schema_version": SOURCE_RECORD_V2_SCHEMA,
            "source_id": args.source_id,
            "source_uri": args.url,
            "retrieved_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "content_sha256": hashlib.sha256(raw).hexdigest(),
            "media_type": "application/json",
            "backend_id": OPENCLI_BACKEND_ID,
            "transformations": ["opencli-public-adapter", f"{args.site}/{args.opencli_command}"],
            "artifact_refs": [artifact.relative_to(project_root).as_posix()],
            "status": "captured",
            "failure_layer": "none",
            "unverified_items": ["adapter output is not independently source-reviewed"],
            "policy": {"public_only": True, "authenticated": False, "submitted_forms": False, "cookies_persisted": False},
            "failure_reason": "",
            "budget": {"pages": 1, "bytes": len(raw), "seconds": round(time.monotonic() - started, 3)},
            "extensions": {"opencli_version": args.opencli_version, "manifest": entry},
        }
        validate_source_record_v2(source)
        record.parent.mkdir(parents=True, exist_ok=True)
        record.write_text(json.dumps(source, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return {"status": "passed", "backend_id": OPENCLI_BACKEND_ID, "result": decoded, "source_record": source}, 0
    except subprocess.TimeoutExpired:
        reason, layer = "opencli timed out", "network"
    except (OSError, ValueError, ExtensionProtocolError) as exc:
        reason = str(exc)
        layer = "policy" if any(token in reason for token in ("public", "forbidden", "domain")) else "configuration"
    return {"status": "blocked", "backend_id": OPENCLI_BACKEND_ID, "failure_layer": layer, "reason": reason}, 2


def _write_new_json(path: Path, project_root: Path, payload: dict[str, Any]) -> None:
    target = _path_within(path, project_root)
    if target.exists():
        raise ExtensionProtocolError("output already exists; refusing overwrite")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _firecrawl_request(endpoint: str, payload: dict[str, Any], *, timeout: float, max_bytes: int) -> dict[str, Any]:
    api_key = os.environ.get("FIRECRAWL_API_KEY", "").strip()
    if not api_key:
        raise ExtensionProtocolError("firecrawl authorization is not configured")
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        "https://api.firecrawl.dev/v1/" + endpoint.lstrip("/"),
        data=body,
        headers={
            "Authorization": "Bearer " + api_key,
            "Content-Type": "application/json",
            "User-Agent": "ds-lite-web/0.2",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read(max_bytes + 1)
            if len(raw) > max_bytes:
                raise ExtensionProtocolError("provider response exceeded byte budget")
            if response.status < 200 or response.status >= 300:
                raise ExtensionProtocolError(f"firecrawl returned HTTP {response.status}")
    except urllib.error.HTTPError as exc:
        raise ExtensionProtocolError(f"firecrawl returned HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise ExtensionProtocolError(f"firecrawl network failure: {exc.reason}") from exc
    try:
        decoded = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ExtensionProtocolError("firecrawl returned invalid JSON") from exc
    if not isinstance(decoded, dict) or decoded.get("success") is False:
        raise ExtensionProtocolError("firecrawl response was not successful")
    return decoded


def _firecrawl_search(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    project_root = Path(args.project_root).expanduser().resolve()
    if not args.authorized_external_provider:
        return {"status": "blocked", "backend_id": "firecrawl", "failure_layer": "authorization", "reason": "explicit external-provider authorization is required"}, 2
    try:
        if not args.allowed_domains:
            raise ExtensionProtocolError("at least one allowed domain is required")
        payload = _firecrawl_request(
            "search",
            {"query": args.query, "limit": args.max_results, "scrapeOptions": {"formats": ["markdown"]}},
            timeout=args.timeout,
            max_bytes=args.max_bytes,
        )
        raw_results = payload.get("data", [])
        if not isinstance(raw_results, list):
            raise ExtensionProtocolError("firecrawl search data must be a list")
        results: list[dict[str, Any]] = []
        for item in raw_results[: args.max_results]:
            if not isinstance(item, dict) or not isinstance(item.get("url"), str):
                continue
            _validate_public_uri(item["url"])
            _validate_run_scope(item["url"], args)
            results.append({
                "url": item["url"],
                "title": str(item.get("title", ""))[:500],
                "description": str(item.get("description", ""))[:2000],
                "content_sha256": hashlib.sha256(str(item.get("markdown", "")).encode("utf-8")).hexdigest()
                if item.get("markdown") else "",
            })
        result = {
            "schema_version": "ds-lite.web-search-result.v1",
            "status": "passed",
            "backend_id": "firecrawl",
            "query": args.query,
            "results": results,
            "budget": {"results": len(results), "seconds": args.timeout, "bytes": args.max_bytes},
            "policy": {"public_only": True, "authenticated_browsing": False, "cookies_persisted": False},
            "extensions": {},
        }
        _write_new_json(Path(args.output), project_root, result)
        return result, 0
    except (OSError, ValueError, ExtensionProtocolError) as exc:
        message = str(exc)
        layer = "configuration" if "authorization" in message else (
            "policy" if "domain" in message or "public" in message else "network"
        )
        return {"status": "blocked", "backend_id": "firecrawl", "failure_layer": layer, "reason": message}, 2


def _firecrawl_render(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    project_root = Path(args.project_root).expanduser().resolve()
    if not args.authorized_external_provider:
        return {"status": "blocked", "backend_id": "firecrawl", "failure_layer": "authorization", "reason": "explicit external-provider authorization is required"}, 2
    try:
        _validate_public_uri(args.url)
        _validate_run_scope(args.url, args)
        response = _firecrawl_request(
            "scrape",
            {"url": args.url, "formats": ["markdown"], "onlyMainContent": True},
            timeout=args.timeout,
            max_bytes=args.max_bytes,
        )
        data = response.get("data")
        if not isinstance(data, dict):
            raise ExtensionProtocolError("firecrawl scrape data is unavailable")
        content = data.get("markdown") or data.get("html") or ""
        if not isinstance(content, str) or not content:
            raise ExtensionProtocolError("firecrawl scrape returned no content")
        content_bytes = content.encode("utf-8")
        artifact = _path_within(Path(args.output), project_root)
        record = _path_within(Path(args.record_output), project_root)
        if artifact.exists() or record.exists():
            raise ExtensionProtocolError("render refuses to overwrite existing outputs")
        artifact.parent.mkdir(parents=True, exist_ok=True)
        artifact.write_bytes(content_bytes)
        source = {
            "schema_version": SOURCE_RECORD_V2_SCHEMA,
            "source_id": args.source_id,
            "source_uri": args.url,
            "retrieved_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "content_sha256": hashlib.sha256(content_bytes).hexdigest(),
            "media_type": "text/markdown" if data.get("markdown") else "text/html",
            "backend_id": "firecrawl",
            "transformations": ["firecrawl-scrape", "main-content"],
            "artifact_refs": [artifact.relative_to(project_root).as_posix()],
            "status": "captured",
            "failure_layer": "none",
            "unverified_items": [],
            "policy": {"public_only": True, "authenticated": False, "submitted_forms": False, "cookies_persisted": False},
            "failure_reason": "",
            "budget": {"pages": 1, "bytes": len(content_bytes), "seconds": args.timeout},
            "extensions": {"requested_uri": args.url},
        }
        validate_source_record_v2(source)
        record.parent.mkdir(parents=True, exist_ok=True)
        record.write_text(json.dumps(source, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return {"status": "passed", "backend_id": "firecrawl", "source_record": source}, 0
    except (OSError, ValueError, ExtensionProtocolError) as exc:
        message = str(exc)
        layer = "configuration" if "authorization" in message else (
            "policy" if "domain" in message or "public" in message else "render"
        )
        return {"status": "blocked", "backend_id": "firecrawl", "failure_layer": layer, "reason": message}, 2


def _benchmark(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    project_root = Path(args.project_root).expanduser().resolve()
    rows: list[dict[str, Any]] = []
    try:
        _validate_run_scope(args.url, args)
    except ExtensionProtocolError as exc:
        return {"status": "blocked", "failure_layer": "policy", "reason": str(exc)}, 2
    for backend_id, available in (("stdlib-http", True), ("firecrawl", bool(os.environ.get("FIRECRAWL_API_KEY")))):
        started = time.monotonic()
        if not available:
            rows.append({"backend_id": backend_id, "status": "not-observed", "failure_layer": "configuration"})
            continue
        try:
            if backend_id == "stdlib-http":
                _, content, media_type = _bounded_fetch(
                    args.url,
                    timeout=args.timeout,
                    max_bytes=args.max_bytes,
                    allowed_domains=args.allowed_domains,
                )
                rows.append({"backend_id": backend_id, "status": "passed", "media_type": media_type, "bytes": len(content), "seconds": round(time.monotonic() - started, 3)})
            else:
                if not args.authorized_external_provider:
                    rows.append({"backend_id": backend_id, "status": "not-observed", "failure_layer": "authorization"})
                    continue
                response = _firecrawl_request("scrape", {"url": args.url, "formats": ["markdown"]}, timeout=args.timeout, max_bytes=args.max_bytes)
                data = response.get("data", {})
                content = str(data.get("markdown") or data.get("html") or "")
                rows.append({"backend_id": backend_id, "status": "passed", "bytes": len(content.encode("utf-8")), "seconds": round(time.monotonic() - started, 3)})
        except (OSError, ValueError, ExtensionProtocolError) as exc:
            rows.append({"backend_id": backend_id, "status": "blocked", "failure_layer": "network", "reason": str(exc)})
    result = {"schema_version": "ds-lite.web-benchmark.v1", "status": "passed" if any(row["status"] == "passed" for row in rows) else "not-observed", "url": args.url, "rows": rows, "budget": {"seconds": args.timeout, "bytes": args.max_bytes}, "extensions": {}}
    try:
        _write_new_json(Path(args.output), project_root, result)
    except (OSError, ValueError, ExtensionProtocolError) as exc:
        return {"status": "blocked", "failure_layer": "storage", "reason": str(exc)}, 2
    return result, 0 if result["status"] == "passed" else 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate DS Lite extension-pack protocols.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    validators: dict[str, Callable[[Any], dict[str, Any]]] = {}
    for command, validator in (
        ("validate-capability", validate_capability),
        ("validate-source-record", validate_source_record),
        ("validate-source-record-v2", validate_source_record_v2),
    ):
        child = subparsers.add_parser(command)
        child.add_argument("--path", required=True)
        validators[command] = validator
    doctor_parser = subparsers.add_parser("doctor")
    doctor_parser.add_argument("--core-root")
    doctor_parser.add_argument("--playwright-module")
    record_parser = subparsers.add_parser("record-source")
    record_parser.add_argument("--project-root", required=True)
    record_parser.add_argument("--artifact", required=True)
    record_parser.add_argument("--output", required=True)
    record_parser.add_argument("--source-id", required=True)
    record_parser.add_argument("--source-uri", required=True)
    record_parser.add_argument("--backend-id", required=True)
    record_parser.add_argument("--media-type", required=True)
    record_parser.add_argument("--transformation", action="append")
    record_parser.add_argument("--unverified-item", action="append")
    record_v2_parser = subparsers.add_parser("record-source-v2")
    for argument in ("project-root", "artifact", "output", "source-id", "source-uri", "backend-id", "media-type"):
        record_v2_parser.add_argument(f"--{argument}", required=True)
    record_v2_parser.add_argument("--transformation", action="append")
    record_v2_parser.add_argument("--unverified-item", action="append")
    fetch_parser = subparsers.add_parser("fetch")
    fetch_parser.add_argument("--url", required=True)
    fetch_parser.add_argument("--project-root", required=True)
    fetch_parser.add_argument("--output", required=True)
    fetch_parser.add_argument("--record-output", required=True)
    fetch_parser.add_argument("--source-id", required=True)
    fetch_parser.add_argument("--backend-id", default="stdlib-http")
    fetch_parser.add_argument("--timeout", type=float, default=20.0)
    fetch_parser.add_argument("--max-bytes", type=int, default=2_000_000)
    fetch_parser.add_argument("--allowed-domain", dest="allowed_domains", action="append", default=[])
    search_parser = subparsers.add_parser("search")
    search_parser.add_argument("--query", required=True)
    search_parser.add_argument("--project-root", required=True)
    search_parser.add_argument("--output", required=True)
    search_parser.add_argument("--max-results", type=int, default=5)
    search_parser.add_argument("--timeout", type=float, default=20.0)
    search_parser.add_argument("--max-bytes", type=int, default=2_000_000)
    search_parser.add_argument("--authorized-external-provider", action="store_true")
    search_parser.add_argument("--allowed-domain", dest="allowed_domains", action="append", default=[])
    render_parser = subparsers.add_parser("render")
    render_parser.add_argument("--url", required=True)
    render_parser.add_argument("--project-root", required=True)
    render_parser.add_argument("--output", required=True)
    render_parser.add_argument("--record-output", required=True)
    render_parser.add_argument("--source-id", required=True)
    render_parser.add_argument("--timeout", type=float, default=30.0)
    render_parser.add_argument("--max-bytes", type=int, default=2_000_000)
    render_parser.add_argument("--authorized-external-provider", action="store_true")
    render_parser.add_argument("--allowed-domain", dest="allowed_domains", action="append", default=[])
    playwright_parser = subparsers.add_parser("render-playwright")
    for argument in ("url", "project-root", "output", "record-output", "source-id", "playwright-module"):
        playwright_parser.add_argument(f"--{argument}", required=True)
    playwright_parser.add_argument("--node-bin", default="node")
    playwright_parser.add_argument("--timeout", type=float, default=30.0)
    playwright_parser.add_argument("--max-bytes", type=int, default=2_000_000)
    playwright_parser.add_argument("--allowed-domain", dest="allowed_domains", action="append", default=[])
    benchmark_parser = subparsers.add_parser("benchmark")
    benchmark_parser.add_argument("--url", required=True)
    benchmark_parser.add_argument("--project-root", required=True)
    benchmark_parser.add_argument("--output", required=True)
    benchmark_parser.add_argument("--timeout", type=float, default=20.0)
    benchmark_parser.add_argument("--max-bytes", type=int, default=2_000_000)
    benchmark_parser.add_argument("--authorized-external-provider", action="store_true")
    benchmark_parser.add_argument("--allowed-domain", dest="allowed_domains", action="append", default=[])
    opencli_parser = subparsers.add_parser("opencli")
    opencli_parser.add_argument("--site", required=True)
    opencli_parser.add_argument("--command", dest="opencli_command", required=True)
    opencli_parser.add_argument("--arg", dest="opencli_arg", action="append", default=[])
    opencli_parser.add_argument("--url", required=True)
    opencli_parser.add_argument("--project-root", required=True)
    opencli_parser.add_argument("--output", required=True)
    opencli_parser.add_argument("--record-output", required=True)
    opencli_parser.add_argument("--source-id", required=True)
    opencli_parser.add_argument("--opencli-version", default="not-observed")
    opencli_parser.add_argument("--timeout", type=float, default=20.0)
    opencli_parser.add_argument("--max-bytes", type=int, default=2_000_000)
    opencli_parser.add_argument("--allowed-domain", dest="allowed_domains", action="append", default=[])
    args = parser.parse_args(argv)
    if args.command == "doctor":
        payload, returncode = doctor(args.core_root)
        payload["backends"] = backend_doctor(args.playwright_module)["backends"]
        _emit_json(payload)
        return returncode
    if args.command == "fetch":
        payload, returncode = fetch_public(args)
        _emit_json(payload)
        return returncode
    if args.command == "search":
        payload, returncode = _firecrawl_search(args)
        _emit_json(payload)
        return returncode
    if args.command == "render":
        payload, returncode = _firecrawl_render(args)
        _emit_json(payload)
        return returncode
    if args.command == "render-playwright":
        payload, returncode = render_playwright(args)
        _emit_json(payload)
        return returncode
    if args.command == "benchmark":
        payload, returncode = _benchmark(args)
        _emit_json(payload)
        return returncode
    if args.command == "opencli":
        payload, returncode = _opencli(args)
        _emit_json(payload)
        return returncode
    if args.command in {"record-source", "record-source-v2"}:
        try:
            payload = record_source(args) if args.command == "record-source" else record_source_v2(args)
        except (OSError, UnicodeError, ExtensionProtocolError) as exc:
            _emit_json({"ok": False, "error": str(exc)})
            return 1
        _emit_json({"ok": True, "schema_version": payload["schema_version"]})
        return 0
    try:
        raw = json.loads(Path(args.path).read_text(encoding="utf-8"))
        validated = validators[args.command](raw)
    except (OSError, UnicodeError, json.JSONDecodeError, ExtensionProtocolError) as exc:
        _emit_json({"ok": False, "error": str(exc)})
        return 1
    _emit_json({"ok": True, "schema_version": validated["schema_version"]})
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
