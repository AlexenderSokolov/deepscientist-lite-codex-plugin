#!/usr/bin/env python3
"""Fresh-only real transport acceptance with redacted round receipts."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

try:
    import pilot_runtime
    import wire_probe
except ModuleNotFoundError:  # pragma: no cover - package import path
    from teaching import pilot_runtime, wire_probe


SCHEMA_VERSION = "ds-lite.real-acceptance.v1"
ROUND_FIELDS = {
    "schema_version",
    "pilot_id",
    "round_id",
    "status",
    "target",
    "facts",
    "hypotheses",
    "authorization_boundary",
    "commands",
    "observations",
    "evidence_refs",
    "failure_layer",
    "unverified",
    "next_action",
    "attempts",
    "created_at",
    "extensions",
}
FORBIDDEN_KEYS = {
    "api_key",
    "auth_json",
    "credential",
    "environment_variables",
    "hidden_reasoning",
    "password",
    "prompt",
    "raw_jsonl",
    "raw_response",
    "secret",
    "stderr",
    "token",
}
ABSOLUTE_WINDOWS = re.compile(r"(?:^|\s)[A-Za-z]:[\\/]")
STATUSES = {"prepared", "passed", "blocked", "failed", "ambiguous"}


class RealAcceptanceError(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _relative_ref(value: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value or ":" in value:
        raise RealAcceptanceError("evidence refs must be relative POSIX paths")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise RealAcceptanceError("evidence refs must stay inside the acceptance root")
    return value


def _scan(value: Any, path: str = "") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = str(key).lower().replace("-", "_")
            if normalized in FORBIDDEN_KEYS:
                raise RealAcceptanceError(f"forbidden sensitive field: {path + '.' if path else ''}{key}")
            _scan(child, f"{path}.{key}" if path else str(key))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _scan(child, f"{path}[{index}]")
    elif isinstance(value, str):
        lowered = value.lower()
        if "http://" in lowered or "https://" in lowered or ABSOLUTE_WINDOWS.search(value):
            raise RealAcceptanceError(f"absolute endpoint or workstation path is forbidden at {path}")


def new_round(
    *,
    pilot_id: str,
    round_id: str,
    status: str,
    target: str,
    facts: list[str],
    hypotheses: list[str],
    authorization_boundary: list[str],
    commands: list[str],
    observations: dict[str, Any],
    evidence_refs: list[str],
    failure_layer: str,
    unverified: list[str],
    next_action: str,
    attempts: dict[str, Any] | None = None,
    extensions: dict[str, Any] | None = None,
) -> dict[str, Any]:
    result = {
        "schema_version": SCHEMA_VERSION,
        "pilot_id": pilot_id,
        "round_id": round_id,
        "status": status,
        "target": target,
        "facts": facts,
        "hypotheses": hypotheses,
        "authorization_boundary": authorization_boundary,
        "commands": commands,
        "observations": observations,
        "evidence_refs": evidence_refs,
        "failure_layer": failure_layer,
        "unverified": unverified,
        "next_action": next_action,
        "attempts": attempts or {},
        "created_at": _now(),
        "extensions": extensions or {},
    }
    return validate_round(result)


def validate_round(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict) or set(payload) != ROUND_FIELDS:
        raise RealAcceptanceError("round receipt fields do not match ds-lite.real-acceptance.v1")
    if payload.get("schema_version") != SCHEMA_VERSION or payload.get("status") not in STATUSES:
        raise RealAcceptanceError("round receipt schema or status is invalid")
    for field in ("facts", "hypotheses", "authorization_boundary", "commands", "unverified"):
        if not isinstance(payload.get(field), list) or not all(isinstance(item, str) and item for item in payload[field]):
            raise RealAcceptanceError(f"{field} must be a list of non-empty strings")
    if not isinstance(payload.get("observations"), dict) or not isinstance(payload.get("attempts"), dict):
        raise RealAcceptanceError("observations and attempts must be objects")
    payload["evidence_refs"] = [_relative_ref(item) for item in payload.get("evidence_refs", [])]
    _scan(payload)
    return payload


def _write_round(root: Path, name: str, payload: dict[str, Any]) -> None:
    path = root / "rounds" / name
    if path.exists():
        raise RealAcceptanceError(f"round already exists; refusing to overwrite: {name}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(validate_round(payload), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _manifest(root: Path) -> dict[str, Any]:
    path = root / "acceptance-manifest.json"
    if not path.is_file():
        raise RealAcceptanceError("acceptance roots have not been prepared")
    return json.loads(path.read_text(encoding="utf-8"))


def _require_round(root: Path, name: str, *, expected_status: str = "passed") -> dict[str, Any]:
    path = root / "rounds" / name
    if not path.is_file():
        raise RealAcceptanceError(f"required previous round is missing: {name}")
    value = json.loads(path.read_text(encoding="utf-8"))
    validate_round(value)
    if value["status"] != expected_status:
        raise RealAcceptanceError(f"required previous round is not {expected_status}: {name}")
    return value


def prepare_roots(
    windows_root: Path | str,
    wsl_root: Path | str,
    *,
    pilot_id: str,
    authorization_ref: str,
) -> dict[str, Any]:
    windows = Path(windows_root)
    wsl = Path(wsl_root)
    try:
        authorization_ref = _relative_ref(authorization_ref)
    except RealAcceptanceError as exc:
        raise RealAcceptanceError("authorization_ref must be a project-relative POSIX path") from exc
    if windows.exists() or wsl.exists():
        raise RealAcceptanceError("acceptance roots must both be fresh")
    windows.mkdir(parents=True)
    wsl.mkdir(parents=True)
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "pilot_id": pilot_id,
        "authorization_ref": authorization_ref,
        "windows_root_ref": ".",
        "wsl_root_ref": "peer",
        "old_pilot_accessed": False,
        "automatic_retry_allowed": False,
        "created_at": _now(),
    }
    (windows / "acceptance-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    (wsl / "peer-manifest.json").write_text(
        json.dumps({"schema_version": SCHEMA_VERSION, "pilot_id": pilot_id, "peer_ref": "windows"}, indent=2) + "\n",
        encoding="utf-8",
    )
    receipt = new_round(
        pilot_id=pilot_id,
        round_id="prepare",
        status="prepared",
        target="create fresh diagnostic roots and freeze the authorization boundary",
        facts=["both output roots were absent before creation", "the frozen predecessor is out of scope"],
        hypotheses=["provider compatibility can be diagnosed without reading predecessor artifacts"],
        authorization_boundary=["fresh roots only", "no cache or credential mutation", "no model request"],
        commands=["real_acceptance prepare"],
        observations={"windows_root_created": True, "wsl_root_created": True, "old_pilot_accessed": False},
        evidence_refs=["acceptance-manifest.json", "rounds/00-prepare.json"],
        failure_layer="none",
        unverified=["provider route", "network", "Responses wire", "Codex wire", "real host"],
        next_action="run the model-free preflight",
        attempts={"provider_request_count": 0},
    )
    _write_round(windows, "00-prepare.json", receipt)
    return receipt


def _command_prefix(path: Path) -> list[str]:
    """Build a command prefix that can execute the given CLI binary."""
    suffix = path.suffix.lower()
    if suffix == ".py":
        return [sys.executable, str(path)]
    if suffix == ".js":
        node = shutil.which("node")
        if node:
            return [node, str(path)]
    return [str(path)]


def _run_cli(path: Path, args: list[str], *, home: Path, environment: dict[str, str], timeout: float = 15.0) -> dict[str, Any]:
    env = os.environ.copy()
    env.update(environment)
    env.update({"CODEX_HOME": str(home), "PYTHONUTF8": "1", "PYTHONDONTWRITEBYTECODE": "1"})
    try:
        completed = subprocess.run(
            [*_command_prefix(path), *args],
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=timeout,
            env=env,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return {"status": "failed", "returncode": None, "output": "", "output_sha256": hashlib.sha256(b"").hexdigest()}
    output = f"{completed.stdout}\n{completed.stderr}"
    return {
        "status": "passed" if completed.returncode == 0 else "failed",
        "returncode": completed.returncode,
        "output": output,
        "output_sha256": hashlib.sha256(output.encode("utf-8")).hexdigest(),
    }


def _contains_model(value: Any, model: str) -> bool:
    if isinstance(value, dict):
        return any(_contains_model(child, model) for child in value.values())
    if isinstance(value, list):
        return any(_contains_model(child, model) for child in value)
    return value == model


def _extract_cli_version(output: str) -> str | None:
    """Extract the CLI version string from codex --version output."""
    match = re.search(r"codex-cli\s+(\S+)", output)
    return match.group(1) if match else None


def preflight_round(
    windows_root: Path | str,
    *,
    source_codex_home: Path | str,
    codex_bin: Path | str,
    expected_cli_sha256: str,
    environment: dict[str, str] | None = None,
) -> dict[str, Any]:
    root = Path(windows_root)
    manifest = _manifest(root)
    _require_round(root, "00-prepare.json", expected_status="prepared")
    if (root / "rounds" / "01-preflight.json").exists():
        raise RealAcceptanceError("preflight round already exists")
    home = root / "wire-home"
    home.mkdir()
    lines, route_status = pilot_runtime.clone_nonsecret_provider_config(Path(source_codex_home), home)
    (home / "config.toml").write_text("\n".join(lines) + "\n", encoding="utf-8")
    binary = Path(codex_bin)
    actual_hash = hashlib.sha256(binary.read_bytes()).hexdigest()
    env = dict(environment or os.environ)
    version = _run_cli(binary, ["--version"], home=home, environment=env)
    features = _run_cli(binary, ["features", "list"], home=home, environment=env)
    models = _run_cli(binary, ["debug", "models"], home=home, environment=env)
    try:
        catalog_payload = json.loads(models["output"].strip())
    except (TypeError, json.JSONDecodeError):
        catalog_payload = None
    required_features = all(term in features["output"] for term in ("hooks", "multi_agent", "plugins"))
    model_observed = _contains_model(catalog_payload, wire_probe.MODEL)
    auth_category = "environment-api-key" if env.get("OPENAI_API_KEY") else "not-observed"
    cli_version = _extract_cli_version(version["output"])
    catalog_configured = route_status.get("catalog_configured", False)
    catalog_ok = route_status.get("catalog_copied", False) if catalog_configured else True
    passed = all(
        (
            actual_hash.lower() == expected_cli_sha256.lower(),
            cli_version is not None and version["status"] == "passed",
            required_features and features["status"] == "passed",
            models["status"] == "passed" and model_observed,
            route_status.get("status") == "copied",
            route_status.get("provider_route_copied") is True,
            catalog_ok,
            auth_category == "environment-api-key",
        )
    )
    observations = {
        "cli_version": cli_version or "unexpected",
        "cli_sha256_match": actual_hash.lower() == expected_cli_sha256.lower(),
        "feature_surface_observed": required_features,
        "catalog_model_observed": model_observed,
        "authentication_category": auth_category,
        "route_fidelity": route_status.get("route_fidelity", {}),
        "catalog_copied": route_status.get("catalog_copied", False),
        "raw_cli_output_persisted": False,
    }
    receipt = new_round(
        pilot_id=manifest["pilot_id"],
        round_id="preflight",
        status="passed" if passed else "blocked",
        target="prove exact CLI, model catalog, authentication category, and provider route fidelity",
        facts=["preflight performs no model request", "the isolated route forces request and stream retries to zero"],
        hypotheses=["preserving requires_openai_auth restores the intended authentication path"],
        authorization_boundary=["read formal non-secret route only", "do not read credential files", "no provider request"],
        commands=["codex --version", "codex features list", "codex debug models"],
        observations=observations,
        evidence_refs=["wire-home/config.toml", "rounds/01-preflight.json"],
        failure_layer="none" if passed else "configuration-or-cli",
        unverified=[] if passed else ["network", "Responses wire", "Codex wire"],
        next_action="run one DNS/TCP/TLS probe" if passed else "stop and correct the failed preflight field",
        attempts={"provider_request_count": 0, "automatic_retry_observed": False},
        extensions={"probe_output_sha256": {"version": version["output_sha256"], "features": features["output_sha256"], "models": models["output_sha256"]}},
    )
    _write_round(root, "01-preflight.json", receipt)
    return receipt


def network_round(
    windows_root: Path | str,
    *,
    source_codex_home: Path | str,
    timeout: float = 5.0,
) -> dict[str, Any]:
    root = Path(windows_root)
    manifest = _manifest(root)
    _require_round(root, "01-preflight.json")
    route = wire_probe.load_provider_route(source_codex_home)
    observed = wire_probe.probe_network(route, timeout=timeout)
    passed = observed["status"] == "passed"
    receipt = new_round(
        pilot_id=manifest["pilot_id"],
        round_id="network",
        status="passed" if passed else "blocked",
        target="observe DNS, TCP, and TLS reachability without a model request",
        facts=["the endpoint value remained in memory", "each network layer was attempted at most once"],
        hypotheses=["a reachable provider should complete the physical connection layers before wire testing"],
        authorization_boundary=["no authentication header", "no HTTP request", "no automatic retry"],
        commands=["single DNS lookup", "single TCP connect", "single TLS handshake when required"],
        observations=observed,
        evidence_refs=["rounds/02-network.json"],
        failure_layer="none" if passed else observed.get("failure_class", "network"),
        unverified=[] if passed else ["Responses wire", "Codex wire"],
        next_action="run one authenticated Responses request" if passed else "freeze this diagnostic identity",
        attempts=observed.get("attempts", {}),
    )
    _write_round(root, "02-network.json", receipt)
    return receipt


def responses_round(
    windows_root: Path | str,
    *,
    source_codex_home: Path | str,
    api_key: str | None = None,
    timeout: float = 30.0,
    responses_lite_header: bool = False,
    input_kind: str = "string",
    request_profile: str = "baseline",
) -> dict[str, Any]:
    root = Path(windows_root)
    manifest = _manifest(root)
    _require_round(root, "02-network.json")
    route = wire_probe.load_provider_route(source_codex_home)
    observed = wire_probe.probe_responses(
        route,
        api_key=api_key or os.environ.get("OPENAI_API_KEY"),
        timeout=timeout,
        responses_lite_header=responses_lite_header,
        input_kind=input_kind,
        request_profile=request_profile,
    )
    passed = observed["status"] == "passed"
    attempts = {
        "provider_request_count": observed["request_count"],
        "automatic_retry_observed": observed["automatic_retry_observed"],
    }
    receipt = new_round(
        pilot_id=manifest["pilot_id"],
        round_id="responses",
        status="passed" if passed else "blocked",
        target="prove one authenticated minimal Responses SSE exchange",
        facts=["the request used the configured Responses route", "raw request and response content were not persisted"],
        hypotheses=["a terminal event with nonzero usage proves provider-level Responses compatibility"],
        authorization_boundary=["one provider request", "no retry", "authentication value remains in memory"],
        commands=["single POST responses stream"],
        observations=observed,
        evidence_refs=["rounds/03-responses.json"],
        failure_layer="none" if passed else observed["diagnostic"].get("failure_class", "transport"),
        unverified=[] if passed else ["Codex CLI wire", "real host", "delegation", "matched effect"],
        next_action="prepare the fresh gated-03 CLI canary" if passed else "freeze this diagnostic identity",
        attempts=attempts,
    )
    _write_round(root, "03-responses.json", receipt)
    return receipt


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run staged DeepScientist Lite real transport acceptance.")
    sub = parser.add_subparsers(dest="action", required=True)
    prepare = sub.add_parser("prepare")
    prepare.add_argument("--windows-root", type=Path, required=True)
    prepare.add_argument("--wsl-root", type=Path, required=True)
    prepare.add_argument("--pilot-id", required=True)
    prepare.add_argument("--authorization-ref", required=True)
    for name in ("preflight", "network", "responses"):
        item = sub.add_parser(name)
        item.add_argument("--windows-root", type=Path, required=True)
        item.add_argument("--source-codex-home", type=Path, required=True)
        item.add_argument("--timeout-seconds", type=float, default=30.0 if name == "responses" else 5.0)
        if name == "preflight":
            item.add_argument("--codex-bin", type=Path, required=True)
            item.add_argument("--expected-cli-sha256", required=True)
        elif name == "responses":
            item.add_argument("--responses-lite-header", action="store_true")
            item.add_argument("--input-kind", choices=("string", "message-array"), default="string")
            item.add_argument("--request-profile", choices=("baseline", "codex-lite-minimal"), default="baseline")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.action == "prepare":
            result = prepare_roots(args.windows_root, args.wsl_root, pilot_id=args.pilot_id, authorization_ref=args.authorization_ref)
        elif args.action == "preflight":
            result = preflight_round(
                args.windows_root,
                source_codex_home=args.source_codex_home,
                codex_bin=args.codex_bin,
                expected_cli_sha256=args.expected_cli_sha256,
            )
        elif args.action == "network":
            result = network_round(args.windows_root, source_codex_home=args.source_codex_home, timeout=args.timeout_seconds)
        else:
            result = responses_round(
                args.windows_root,
                source_codex_home=args.source_codex_home,
                timeout=args.timeout_seconds,
                responses_lite_header=args.responses_lite_header,
                input_kind=args.input_kind,
                request_profile=args.request_profile,
            )
    except (RealAcceptanceError, wire_probe.WireProbeError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({"schema_version": result["schema_version"], "round_id": result["round_id"], "status": result["status"]}, sort_keys=True))
    return 0 if result["status"] in {"prepared", "passed"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
