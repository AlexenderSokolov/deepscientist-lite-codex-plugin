#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any


SCHEMA = "ds-lite.engineering-analysis.v1"
CORE = {"plugin": "deepscientist-lite", "version": "0.9.0-beta.1"}
BACKEND_STATUSES = {"available", "unavailable", "not-observed"}
CHECK_STATUSES = {"passed", "failed", "warning", "not-observed"}
REQUIRED_CHECKS = {"units", "dimensions", "aliasing", "leakage", "figure_axes"}
ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")


class EngineeringProtocolError(ValueError):
    pass


def _safe_ref(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise EngineeringProtocolError(f"{label} must be a non-empty project-relative reference")
    posix = PurePosixPath(value.replace("\\", "/"))
    if posix.is_absolute() or PureWindowsPath(value).is_absolute() or ".." in posix.parts:
        raise EngineeringProtocolError(f"{label} must be project-relative")
    return posix.as_posix()


def _string_list(value: Any, label: str, *, nonempty: bool = True) -> None:
    if not isinstance(value, list) or (nonempty and not value) or not all(isinstance(item, str) and item.strip() for item in value):
        raise EngineeringProtocolError(f"{label} must be a{' non-empty' if nonempty else ''} string list")


def validate_analysis(payload: Any) -> dict[str, Any]:
    required = {
        "schema_version", "analysis_id", "task", "backend", "units", "sampling", "preprocessing",
        "fft", "simulation", "checks", "commands", "artifact_refs", "evidence_pack_ref", "extensions",
    }
    if not isinstance(payload, dict) or set(payload) != required:
        raise EngineeringProtocolError("engineering analysis fields are invalid")
    if payload["schema_version"] != SCHEMA:
        raise EngineeringProtocolError("engineering schema is unsupported")
    if not isinstance(payload["analysis_id"], str) or not ID_RE.fullmatch(payload["analysis_id"]):
        raise EngineeringProtocolError("analysis_id is invalid")
    if not isinstance(payload["task"], str) or not payload["task"].strip():
        raise EngineeringProtocolError("task must be non-empty")

    backend = payload["backend"]
    if not isinstance(backend, dict) or set(backend) != {"name", "status", "version"}:
        raise EngineeringProtocolError("backend fields are invalid")
    if not isinstance(backend["name"], str) or not backend["name"] or backend["status"] not in BACKEND_STATUSES or not isinstance(backend["version"], str):
        raise EngineeringProtocolError("backend is invalid")

    units = payload["units"]
    if not isinstance(units, dict) or set(units) != {"time", "signal", "frequency"}:
        raise EngineeringProtocolError("units must contain time, signal, and frequency")
    if not all(isinstance(value, str) and value for value in units.values()):
        raise EngineeringProtocolError("units must be non-empty strings")
    if units["frequency"].casefold() not in {"hz", "khz", "mhz", "ghz", "rad/s"}:
        raise EngineeringProtocolError("frequency unit is invalid")

    sampling = payload["sampling"]
    if not isinstance(sampling, dict) or not {"rate_hz", "sample_count", "duration_s"}.issubset(sampling) or not set(sampling).issubset({"rate_hz", "sample_count", "duration_s", "max_signal_frequency_hz"}):
        raise EngineeringProtocolError("sampling fields are invalid")
    rate = sampling["rate_hz"]
    count = sampling["sample_count"]
    duration = sampling["duration_s"]
    if not isinstance(rate, (int, float)) or isinstance(rate, bool) or rate <= 0:
        raise EngineeringProtocolError("sampling.rate_hz must be positive")
    if not isinstance(count, int) or isinstance(count, bool) or count < 2:
        raise EngineeringProtocolError("sampling.sample_count must be at least 2")
    if not isinstance(duration, (int, float)) or isinstance(duration, bool) or duration <= 0:
        raise EngineeringProtocolError("sampling.duration_s must be positive")
    if not math.isclose(float(duration), float(count) / float(rate), rel_tol=1e-6, abs_tol=1e-9):
        raise EngineeringProtocolError("sampling duration conflicts with rate_hz and sample_count")
    maximum = sampling.get("max_signal_frequency_hz")
    if maximum is not None:
        if not isinstance(maximum, (int, float)) or isinstance(maximum, bool) or maximum < 0:
            raise EngineeringProtocolError("max_signal_frequency_hz is invalid")
        if maximum >= rate / 2:
            raise EngineeringProtocolError("declared signal frequency creates aliasing risk")

    _string_list(payload["preprocessing"], "preprocessing", nonempty=False)
    fft = payload["fft"]
    if not isinstance(fft, dict) or set(fft) != {"window", "resolution_hz", "scaling"}:
        raise EngineeringProtocolError("fft fields are invalid")
    if not isinstance(fft["window"], str) or not fft["window"] or not isinstance(fft["scaling"], str) or not fft["scaling"]:
        raise EngineeringProtocolError("fft window and scaling are required")
    expected_resolution = float(rate) / count
    if not isinstance(fft["resolution_hz"], (int, float)) or isinstance(fft["resolution_hz"], bool) or not math.isclose(float(fft["resolution_hz"]), expected_resolution, rel_tol=1e-6, abs_tol=1e-9):
        raise EngineeringProtocolError("fft resolution must equal rate_hz / sample_count")

    simulation = payload["simulation"]
    if not isinstance(simulation, dict) or set(simulation) != {"used", "random_seed"} or not isinstance(simulation["used"], bool):
        raise EngineeringProtocolError("simulation fields are invalid")
    seed = simulation["random_seed"]
    if simulation["used"] and (not isinstance(seed, int) or isinstance(seed, bool)):
        raise EngineeringProtocolError("simulation random_seed is required")
    if not simulation["used"] and seed is not None and (not isinstance(seed, int) or isinstance(seed, bool)):
        raise EngineeringProtocolError("random_seed must be an integer or null")

    checks = payload["checks"]
    if not isinstance(checks, dict) or set(checks) != REQUIRED_CHECKS or any(value not in CHECK_STATUSES for value in checks.values()):
        raise EngineeringProtocolError("checks must contain units, dimensions, aliasing, leakage, and figure_axes")
    _string_list(payload["commands"], "commands")
    _string_list(payload["artifact_refs"], "artifact_refs")
    for ref in payload["artifact_refs"]:
        _safe_ref(ref, "artifact_refs")
    _safe_ref(payload["evidence_pack_ref"], "evidence_pack_ref")
    if not isinstance(payload["extensions"], dict):
        raise EngineeringProtocolError("extensions must be an object")
    return json.loads(json.dumps(payload))


def doctor(core_root: str | None) -> tuple[dict[str, Any], int]:
    raw = core_root or os.environ.get("DS_LITE_CORE_ROOT", "").strip()
    result = {"schema_version": "ds-lite.pack-doctor.v1", "pack": "deepscientist-lite-engineering", "required": CORE, "status": "blocked"}
    if not raw:
        result["reason"] = "core-root-not-provided"
        return result, 2
    try:
        manifest = json.loads((Path(raw).expanduser().resolve() / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        result["reason"] = "core-manifest-unavailable"
        return result, 2
    observed = {"plugin": manifest.get("name"), "version": manifest.get("version")}
    result["observed"] = observed
    if observed != CORE:
        result["reason"] = "incompatible-core"
        return result, 2
    result.update({"status": "passed", "reason": "compatible-core-observed"})
    return result, 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate DS Lite engineering protocols.")
    sub = parser.add_subparsers(dest="command", required=True)
    doctor_parser = sub.add_parser("doctor")
    doctor_parser.add_argument("--core-root")
    validate_parser = sub.add_parser("validate")
    validate_parser.add_argument("--path", required=True)
    args = parser.parse_args(argv)
    if args.command == "doctor":
        result, code = doctor(args.core_root)
        print(json.dumps(result, ensure_ascii=False))
        return code
    try:
        validated = validate_analysis(json.loads(Path(args.path).read_text(encoding="utf-8")))
    except (OSError, UnicodeError, json.JSONDecodeError, EngineeringProtocolError) as exc:
        print(json.dumps({"status": "blocked", "error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps({"status": "passed", "schema_version": validated["schema_version"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
