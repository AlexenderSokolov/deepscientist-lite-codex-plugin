#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Iterator

CONTRACT_SCHEMA = "ds-lite.experiment-contract.v1"
EVIDENCE_SCHEMA = "ds-lite.evidence.v1"
ENVIRONMENT_SCHEMA = "ds-lite.environment.v1"
RUN_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
EXTERNAL_URI_RE = re.compile(r"^external://([a-z][a-z0-9_-]*)/(.+)$")
LOCK_TIMEOUT_SECONDS = float(os.environ.get("DS_LITE_LOCK_TIMEOUT", "10"))
CONTRACT_REQUIRED = {
    "schema_version",
    "run_id",
    "node_id",
    "hypothesis",
    "command",
    "cwd",
    "inputs",
    "metrics",
    "seeds",
    "budget",
    "expected_outputs",
    "failure_interpretation",
}
CONTRACT_ALLOWED = CONTRACT_REQUIRED | {"created_at"}
ENVIRONMENT_ALLOWED = {
    "schema_version",
    "python",
    "platform",
    "packages",
    "container",
    "hardware",
    "notes",
}
SENSITIVE_KEYS = {
    "env",
    "environment_variables",
    "token",
    "secret",
    "password",
    "api_key",
    "apikey",
    "credential",
    "credentials",
    "access_key",
    "private_key",
    "client_secret",
    "authorization",
    "cookie",
}


class EvidenceError(Exception):
    pass


def configure_text_streams() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(errors="backslashreplace")
            except (AttributeError, OSError):
                pass


def emit(payload: dict[str, Any], *, stream: Any = sys.stdout) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2), file=stream)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_utc(value: Any, label: str) -> str:
    if not isinstance(value, str):
        raise EvidenceError(f"{label} must be an ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise EvidenceError(f"{label} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise EvidenceError(f"{label} must include a timezone")
    return parsed.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def canonical_root(value: str) -> Path:
    root = Path(value).expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise EvidenceError(f"project root does not exist or is not a directory: {root}")
    return root


def validate_run_id(value: Any) -> str:
    if not isinstance(value, str) or not RUN_ID_RE.fullmatch(value):
        raise EvidenceError("run_id must match [a-z0-9][a-z0-9._-]{0,63}")
    return value


def validate_relative(raw: str) -> str:
    posix = PurePosixPath(raw.replace("\\", "/"))
    if posix.is_absolute() or not posix.parts or any(part in {"", ".", ".."} for part in posix.parts):
        raise EvidenceError(f"path must be normalized and project-relative without '..': {raw}")
    return posix.as_posix()


def normalize_protocol_path(value: Any, *, allow_external: bool = True, allow_dot: bool = False) -> str:
    if not isinstance(value, str) or not value.strip():
        raise EvidenceError("path values must be non-empty strings")
    raw = value.strip().replace("\\", "/")
    if raw == "." and allow_dot:
        return "."
    match = EXTERNAL_URI_RE.fullmatch(raw)
    if match:
        if not allow_external:
            raise EvidenceError(f"external paths are not allowed here: {raw}")
        alias, remainder = match.groups()
        return f"external://{alias}/{validate_relative(remainder)}"
    if Path(raw).expanduser().is_absolute() or PureWindowsPath(raw).is_absolute():
        raise EvidenceError(f"absolute paths are forbidden; use external://alias/path: {raw}")
    return validate_relative(raw)


def resolve_protocol_path(root: Path, value: str) -> tuple[Path | None, str | None, bool]:
    match = EXTERNAL_URI_RE.fullmatch(value)
    if match:
        alias, remainder = match.groups()
        env_name = "DS_LITE_EXTERNAL_" + re.sub(r"[^A-Z0-9]", "_", alias.upper())
        mapped = os.environ.get(env_name, "").strip()
        if not mapped:
            return None, f"{env_name} is not set", True
        mapped_root = Path(mapped).expanduser()
        if not mapped_root.is_absolute():
            return None, f"{env_name} must contain an absolute path", True
        mapped_root = mapped_root.resolve()
        resolved = (mapped_root / PurePosixPath(remainder)).resolve()
        try:
            resolved.relative_to(mapped_root)
        except ValueError:
            return None, f"external path escapes {env_name}", True
        return resolved, None, True
    resolved = (root / PurePosixPath(value)).resolve()
    try:
        resolved.relative_to(root)
    except ValueError:
        return None, "project-relative path resolves outside the project root", False
    return resolved, None, False


def evidence_dir(root: Path, run_id: str) -> Path:
    return root / "research" / "evidence" / run_id


def manifest_path(root: Path, run_id: str) -> Path:
    return evidence_dir(root, run_id) / "manifest.json"


def atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    with temporary.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def atomic_write_json(path: Path, payload: Any) -> None:
    atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


@contextmanager
def evidence_lock(root: Path, run_id: str, timeout: float = LOCK_TIMEOUT_SECONDS) -> Iterator[None]:
    directory = evidence_dir(root, run_id)
    directory.mkdir(parents=True, exist_ok=True)
    handle = (directory / "evidence.lock").open("a+b")
    handle.seek(0, os.SEEK_END)
    if handle.tell() == 0:
        handle.write(b"0")
        handle.flush()
    deadline = time.monotonic() + timeout
    acquired = False
    try:
        while not acquired:
            try:
                handle.seek(0)
                if os.name == "nt":
                    import msvcrt

                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired = True
            except OSError:
                if time.monotonic() >= deadline:
                    raise EvidenceError(f"timed out waiting for evidence lock: {directory / 'evidence.lock'}")
                time.sleep(0.05)
        yield
    finally:
        if acquired:
            handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()


def read_json(path: Path, label: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise EvidenceError(f"{label} not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise EvidenceError(f"{label} is not valid JSON: {path}: {exc}") from exc


def find_sensitive_key(value: Any, prefix: str = "") -> str | None:
    if isinstance(value, dict):
        for key, item in value.items():
            normalized = re.sub(r"[^a-z0-9]+", "_", str(key).lower()).strip("_")
            location = f"{prefix}.{key}" if prefix else str(key)
            if (
                normalized in SENSITIVE_KEYS
                or normalized.endswith("_token")
                or normalized.endswith("_password")
                or normalized.endswith("_secret")
                or normalized.endswith("_api_key")
                or normalized.endswith("_credential")
            ):
                return location
            found = find_sensitive_key(item, location)
            if found:
                return found
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found = find_sensitive_key(item, f"{prefix}[{index}]")
            if found:
                return found
    return None


def validate_metric_specs(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value:
        raise EvidenceError("metrics must be a non-empty list")
    result: list[dict[str, Any]] = []
    names: set[str] = set()
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise EvidenceError(f"metrics[{index}] must be an object")
        unknown = set(item) - {"name", "direction", "threshold", "tolerance"}
        if unknown:
            raise EvidenceError(f"metrics[{index}] has unsupported fields: {', '.join(sorted(unknown))}")
        name = item.get("name")
        direction = item.get("direction")
        if not isinstance(name, str) or not name.strip():
            raise EvidenceError(f"metrics[{index}].name must be non-empty")
        if name in names:
            raise EvidenceError(f"duplicate metric name: {name}")
        names.add(name)
        if direction not in {"max", "min", "target", "observe"}:
            raise EvidenceError(f"metrics[{index}].direction must be max, min, target, or observe")
        threshold = item.get("threshold")
        tolerance = item.get("tolerance")
        if direction == "observe":
            if threshold is not None or tolerance is not None:
                raise EvidenceError(f"observe metric {name} must not define threshold or tolerance")
        elif not isinstance(threshold, (int, float)) or isinstance(threshold, bool):
            raise EvidenceError(f"metric {name} requires a numeric threshold")
        if direction == "target":
            if not isinstance(tolerance, (int, float)) or isinstance(tolerance, bool) or tolerance < 0:
                raise EvidenceError(f"target metric {name} requires a non-negative tolerance")
        elif tolerance is not None:
            raise EvidenceError(f"metric {name} may only define tolerance when direction is target")
        result.append(dict(item))
    return result


def validate_contract(payload: Any, expected_run_id: str) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise EvidenceError("contract must contain a JSON object")
    missing = CONTRACT_REQUIRED - set(payload)
    unknown = set(payload) - CONTRACT_ALLOWED
    if missing:
        raise EvidenceError(f"contract missing fields: {', '.join(sorted(missing))}")
    if unknown:
        raise EvidenceError(f"contract has unsupported fields: {', '.join(sorted(unknown))}")
    sensitive = find_sensitive_key(payload)
    if sensitive:
        raise EvidenceError(f"contract contains a sensitive field name: {sensitive}")
    if payload.get("schema_version") != CONTRACT_SCHEMA:
        raise EvidenceError(f"contract schema_version must be {CONTRACT_SCHEMA}")
    run_id = validate_run_id(payload.get("run_id"))
    if run_id != expected_run_id:
        raise EvidenceError(f"contract run_id {run_id!r} does not match --run-id {expected_run_id!r}")
    for field in ("node_id", "hypothesis", "command", "failure_interpretation"):
        if not isinstance(payload.get(field), str) or not payload[field].strip():
            raise EvidenceError(f"contract {field} must be a non-empty string")
    cwd = normalize_protocol_path(payload.get("cwd"), allow_external=False, allow_dot=True)
    inputs = payload.get("inputs")
    outputs = payload.get("expected_outputs")
    if not isinstance(inputs, list) or not all(isinstance(item, str) for item in inputs):
        raise EvidenceError("contract inputs must be a list of paths")
    if not isinstance(outputs, list) or not all(isinstance(item, str) for item in outputs):
        raise EvidenceError("contract expected_outputs must be a list of paths")
    normalized_inputs = [normalize_protocol_path(item) for item in inputs]
    normalized_outputs = [normalize_protocol_path(item) for item in outputs]
    if len(normalized_inputs) != len(set(normalized_inputs)):
        raise EvidenceError("contract inputs contain duplicate paths")
    if len(normalized_outputs) != len(set(normalized_outputs)):
        raise EvidenceError("contract expected_outputs contain duplicate paths")
    seeds = payload.get("seeds")
    if not isinstance(seeds, list) or any(
        isinstance(item, bool) or not isinstance(item, (int, str)) or (isinstance(item, str) and not item.strip())
        for item in seeds
    ):
        raise EvidenceError("contract seeds must be a list of integers or non-empty strings")
    budget = payload.get("budget")
    if not isinstance(budget, dict) or set(budget) != {"value", "unit"}:
        raise EvidenceError("contract budget must contain exactly value and unit")
    if not isinstance(budget.get("value"), (int, float)) or isinstance(budget.get("value"), bool) or budget["value"] < 0:
        raise EvidenceError("contract budget.value must be a non-negative number")
    if not isinstance(budget.get("unit"), str) or not budget["unit"].strip():
        raise EvidenceError("contract budget.unit must be non-empty")
    created = parse_utc(payload["created_at"], "contract created_at") if payload.get("created_at") else utc_now()
    return {
        "schema_version": CONTRACT_SCHEMA,
        "run_id": run_id,
        "node_id": payload["node_id"].strip(),
        "hypothesis": payload["hypothesis"].strip(),
        "command": payload["command"].strip(),
        "cwd": cwd,
        "inputs": normalized_inputs,
        "metrics": validate_metric_specs(payload["metrics"]),
        "seeds": payload["seeds"],
        "budget": {"value": budget["value"], "unit": budget["unit"].strip()},
        "expected_outputs": normalized_outputs,
        "failure_interpretation": payload["failure_interpretation"].strip(),
        "created_at": created,
    }


def validate_environment(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise EvidenceError("environment snapshot must contain a JSON object")
    unknown = set(payload) - ENVIRONMENT_ALLOWED
    if unknown:
        raise EvidenceError(f"environment snapshot has unsupported fields: {', '.join(sorted(unknown))}")
    if payload.get("schema_version") != ENVIRONMENT_SCHEMA:
        raise EvidenceError(f"environment schema_version must be {ENVIRONMENT_SCHEMA}")
    sensitive = find_sensitive_key(payload)
    if sensitive:
        raise EvidenceError(f"environment snapshot contains a sensitive field name: {sensitive}")
    return payload


def validate_metrics(payload: Any, contract: dict[str, Any]) -> dict[str, float]:
    if not isinstance(payload, dict):
        raise EvidenceError("metrics file must contain an object mapping metric names to numbers")
    result: dict[str, float] = {}
    for key, value in payload.items():
        if not isinstance(key, str) or not key.strip():
            raise EvidenceError("metric result names must be non-empty strings")
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise EvidenceError(f"metric result {key} must be numeric")
        result[key] = float(value)
    expected = {item["name"] for item in contract["metrics"]}
    missing = expected - set(result)
    if missing:
        raise EvidenceError(f"metrics file is missing required metrics: {', '.join(sorted(missing))}")
    return result


def hash_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def file_record(root: Path, role: str, protocol_path: str, *, hash_external: bool = False) -> dict[str, Any]:
    resolved, problem, is_external = resolve_protocol_path(root, protocol_path)
    if problem:
        raise EvidenceError(f"cannot resolve {protocol_path}: {problem}")
    if resolved is None or not resolved.exists() or not resolved.is_file():
        raise EvidenceError(f"evidence file does not exist: {protocol_path}")
    record: dict[str, Any] = {"role": role, "path": protocol_path, "size": resolved.stat().st_size, "sha256": None}
    if not is_external or hash_external:
        record["sha256"], record["size"] = hash_file(resolved)
    return record


def load_contract_and_manifest(root: Path, run_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    directory = evidence_dir(root, run_id)
    contract = validate_contract(read_json(directory / "contract.json", "contract"), run_id)
    manifest = read_json(directory / "manifest.json", "manifest")
    if not isinstance(manifest, dict) or manifest.get("schema_version") != EVIDENCE_SCHEMA:
        raise EvidenceError(f"manifest schema_version must be {EVIDENCE_SCHEMA}")
    if manifest.get("run_id") != run_id or manifest.get("node_id") != contract["node_id"]:
        raise EvidenceError("manifest identifiers do not match the contract")
    return contract, manifest


def cmd_init(args: argparse.Namespace) -> int:
    root = canonical_root(args.root)
    run_id = validate_run_id(args.run_id)
    contract_input = read_json(Path(args.contract), "contract input")
    contract = validate_contract(contract_input, run_id)
    directory = evidence_dir(root, run_id)
    contract_target = directory / "contract.json"
    manifest_target = directory / "manifest.json"
    with evidence_lock(root, run_id):
        if contract_target.exists() or manifest_target.exists():
            existing_contract, existing_manifest = load_contract_and_manifest(root, run_id)
            if isinstance(contract_input, dict) and not contract_input.get("created_at"):
                contract["created_at"] = existing_contract["created_at"]
            if existing_contract != contract:
                raise EvidenceError(f"run {run_id} already exists with a different contract")
            emit({"ok": True, "created": False, "run_id": run_id, "status": existing_manifest.get("status")})
            return 0
        atomic_write_json(contract_target, contract)
        relative_contract = contract_target.relative_to(root).as_posix()
        contract_sha, contract_size = hash_file(contract_target)
        now = utc_now()
        manifest = {
            "schema_version": EVIDENCE_SCHEMA,
            "run_id": run_id,
            "node_id": contract["node_id"],
            "contract_path": relative_contract,
            "status": "planned",
            "created_at": now,
            "updated_at": now,
            "execution": {
                "started_at": None,
                "finished_at": None,
                "exit_code": None,
                "stdout_path": None,
                "stderr_path": None,
                "metrics_path": None,
                "environment_path": None,
            },
            "files": [{"role": "contract", "path": relative_contract, "size": contract_size, "sha256": contract_sha}],
            "verification": {"status": "not-run", "checked_at": None, "errors": [], "warnings": [], "thresholds": []},
        }
        atomic_write_json(manifest_target, manifest)
    emit({"ok": True, "created": True, "run_id": run_id, "manifest": manifest_target.relative_to(root).as_posix()})
    return 0


def copy_text_file(source: Path, target: Path) -> None:
    if source.resolve() == target.resolve():
        return
    try:
        content = source.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise EvidenceError(f"text evidence must be UTF-8: {source}") from exc
    atomic_write_text(target, content)


def cmd_finalize(args: argparse.Namespace) -> int:
    root = canonical_root(args.root)
    run_id = validate_run_id(args.run_id)
    with evidence_lock(root, run_id):
        contract, manifest = load_contract_and_manifest(root, run_id)
        directory = evidence_dir(root, run_id)
        stdout_source = Path(args.stdout).expanduser().resolve()
        stderr_source = Path(args.stderr).expanduser().resolve()
        metrics_source = Path(args.metrics).expanduser().resolve()
        for label, source in (("stdout", stdout_source), ("stderr", stderr_source), ("metrics", metrics_source)):
            if not source.exists() or not source.is_file():
                raise EvidenceError(f"{label} input file does not exist: {source}")
        copy_text_file(stdout_source, directory / "stdout.log")
        copy_text_file(stderr_source, directory / "stderr.log")
        metrics = validate_metrics(read_json(metrics_source, "metrics input"), contract)
        atomic_write_json(directory / "metrics.json", metrics)
        environment = validate_environment(read_json(Path(args.environment), "environment input"))
        atomic_write_json(directory / "environment.json", environment)
        environment_relative = (directory / "environment.json").relative_to(root).as_posix()
        base = directory.relative_to(root).as_posix()
        stdout_relative = f"{base}/stdout.log"
        stderr_relative = f"{base}/stderr.log"
        metrics_relative = f"{base}/metrics.json"
        records = [
            file_record(root, "contract", f"{base}/contract.json"),
            file_record(root, "stdout", stdout_relative),
            file_record(root, "stderr", stderr_relative),
            file_record(root, "metrics", metrics_relative),
        ]
        for input_path in contract["inputs"]:
            records.append(file_record(root, "input", input_path, hash_external=args.hash_external))
        records.append(file_record(root, "environment", environment_relative))
        outputs: list[str] = []
        for value in args.output:
            normalized = normalize_protocol_path(value)
            if normalized in outputs:
                continue
            outputs.append(normalized)
            records.append(file_record(root, "output", normalized, hash_external=args.hash_external))
        started = parse_utc(args.started_at, "started_at") if args.started_at else manifest.get("execution", {}).get("started_at") or utc_now()
        finished = parse_utc(args.finished_at, "finished_at") if args.finished_at else manifest.get("execution", {}).get("finished_at") or utc_now()
        if parse_utc(finished, "finished_at") < parse_utc(started, "started_at"):
            raise EvidenceError("finished_at must not precede started_at")
        execution = {
            "started_at": started,
            "finished_at": finished,
            "exit_code": args.exit_code,
            "stdout_path": stdout_relative,
            "stderr_path": stderr_relative,
            "metrics_path": metrics_relative,
            "environment_path": environment_relative,
        }
        changed = manifest.get("execution") != execution or manifest.get("files") != records
        manifest["status"] = "completed" if args.exit_code == 0 else "failed"
        manifest["updated_at"] = utc_now()
        manifest["execution"] = execution
        manifest["files"] = records
        manifest["verification"] = {"status": "not-run", "checked_at": None, "errors": [], "warnings": [], "thresholds": []}
        atomic_write_json(manifest_path(root, run_id), manifest)
    emit({"ok": True, "changed": changed, "run_id": run_id, "status": manifest["status"], "outputs": outputs})
    return 0


def threshold_results(contract: dict[str, Any], metrics: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    results: list[dict[str, Any]] = []
    warnings: list[str] = []
    for spec in contract["metrics"]:
        name = spec["name"]
        value = metrics.get(name)
        passed: bool | None
        if spec["direction"] == "observe":
            passed = None
        elif spec["direction"] == "max":
            passed = value >= spec["threshold"]
        elif spec["direction"] == "min":
            passed = value <= spec["threshold"]
        else:
            passed = abs(value - spec["threshold"]) <= spec["tolerance"]
        result = {"name": name, "value": value, "direction": spec["direction"], "passed": passed}
        if "threshold" in spec:
            result["threshold"] = spec["threshold"]
        if "tolerance" in spec:
            result["tolerance"] = spec["tolerance"]
        results.append(result)
        if passed is False:
            warnings.append(f"metric {name} did not meet its contract threshold")
    return results, warnings


def verify_pack(root: Path, run_id: str) -> tuple[dict[str, Any], list[str], list[str], list[dict[str, Any]]]:
    contract, manifest = load_contract_and_manifest(root, run_id)
    errors: list[str] = []
    warnings: list[str] = []
    if manifest.get("status") == "planned":
        warnings.append("run has not been finalized")
    records = manifest.get("files")
    if not isinstance(records, list):
        errors.append("manifest files must be a list")
        records = []
    roles: set[str] = set()
    output_paths: set[str] = set()
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            errors.append(f"manifest files[{index}] must be an object")
            continue
        role = record.get("role")
        path_value = record.get("path")
        if not isinstance(role, str) or not isinstance(path_value, str):
            errors.append(f"manifest files[{index}] must define role and path")
            continue
        roles.add(role)
        if role == "output":
            output_paths.add(path_value)
        try:
            normalized = normalize_protocol_path(path_value)
        except EvidenceError as exc:
            errors.append(f"manifest file path is invalid: {path_value!r}: {exc}")
            continue
        if normalized != path_value:
            errors.append(f"manifest file path is not normalized: {path_value}")
        resolved, problem, is_external = resolve_protocol_path(root, normalized)
        if problem:
            errors.append(f"cannot resolve {normalized}: {problem}")
            continue
        if resolved is None or not resolved.exists() or not resolved.is_file():
            errors.append(f"manifest file does not exist: {normalized}")
            continue
        expected_size = record.get("size")
        if expected_size != resolved.stat().st_size:
            errors.append(f"file size changed: {normalized}")
        expected_hash = record.get("sha256")
        if expected_hash:
            actual_hash, _ = hash_file(resolved)
            if actual_hash != expected_hash:
                errors.append(f"file hash changed: {normalized}")
        elif is_external:
            warnings.append(f"external file was recorded without a hash: {normalized}")
        else:
            errors.append(f"project-local file is missing sha256: {normalized}")
    if manifest.get("status") != "planned":
        for role in ("contract", "stdout", "stderr", "metrics", "environment"):
            if role not in roles:
                errors.append(f"manifest is missing required {role} evidence")
    for expected in contract["expected_outputs"]:
        if expected not in output_paths:
            warnings.append(f"expected output was not recorded: {expected}")
    thresholds: list[dict[str, Any]] = []
    metrics_path_value = manifest.get("execution", {}).get("metrics_path")
    if metrics_path_value:
        resolved, problem, _ = resolve_protocol_path(root, metrics_path_value)
        if problem or resolved is None:
            errors.append(f"cannot resolve metrics file: {problem or metrics_path_value}")
        else:
            try:
                metrics = validate_metrics(read_json(resolved, "metrics"), contract)
            except EvidenceError as exc:
                errors.append(str(exc))
            else:
                thresholds, threshold_warnings = threshold_results(contract, metrics)
                warnings.extend(threshold_warnings)
    return manifest, errors, warnings, thresholds


def cmd_verify(args: argparse.Namespace) -> int:
    root = canonical_root(args.root)
    run_id = validate_run_id(args.run_id)
    with evidence_lock(root, run_id):
        manifest, errors, warnings, thresholds = verify_pack(root, run_id)
        failed = bool(errors or (args.strict and warnings))
        manifest["verification"] = {
            "status": "fail" if errors else "warning" if warnings else "pass",
            "checked_at": utc_now(),
            "errors": errors,
            "warnings": warnings,
            "thresholds": thresholds,
        }
        manifest["updated_at"] = utc_now()
        atomic_write_json(manifest_path(root, run_id), manifest)
    emit(
        {
            "ok": not failed,
            "run_id": run_id,
            "status": manifest["verification"]["status"],
            "strict": args.strict,
            "errors": errors,
            "warnings": warnings,
            "thresholds": thresholds,
        }
    )
    return 1 if failed else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Create and verify DeepScientist Lite Evidence Pack v1 records.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init = subparsers.add_parser("init", help="Validate a contract and initialize an evidence pack.")
    init.add_argument("--root", default=".")
    init.add_argument("--run-id", required=True)
    init.add_argument("--contract", required=True, help="UTF-8 JSON experiment contract input.")
    init.set_defaults(func=cmd_init)

    finalize = subparsers.add_parser("finalize", help="Finalize a run with logs, metrics, environment, and outputs.")
    finalize.add_argument("--root", default=".")
    finalize.add_argument("--run-id", required=True)
    finalize.add_argument("--exit-code", required=True, type=int)
    finalize.add_argument("--stdout", required=True)
    finalize.add_argument("--stderr", required=True)
    finalize.add_argument("--metrics", required=True)
    finalize.add_argument("--environment", required=True, help="Allowlisted ds-lite.environment.v1 JSON file.")
    finalize.add_argument("--output", action="append", default=[], help="Project-relative or external:// output path.")
    finalize.add_argument("--hash-external", action="store_true", help="Explicitly hash external:// output files.")
    finalize.add_argument("--started-at", default="")
    finalize.add_argument("--finished-at", default="")
    finalize.set_defaults(func=cmd_finalize)

    verify = subparsers.add_parser("verify", help="Recheck evidence files, hashes, metrics, and expected outputs.")
    verify.add_argument("--root", default=".")
    verify.add_argument("--run-id", required=True)
    verify.add_argument("--strict", action="store_true", help="Treat warnings as verification failure.")
    verify.set_defaults(func=cmd_verify)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args))
    except (EvidenceError, OSError, UnicodeError) as exc:
        emit({"ok": False, "error": str(exc)}, stream=sys.stderr)
        return 1


if __name__ == "__main__":
    configure_text_streams()
    raise SystemExit(main())
