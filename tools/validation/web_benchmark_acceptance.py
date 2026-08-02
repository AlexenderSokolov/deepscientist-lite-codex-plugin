#!/usr/bin/env python3
"""Aggregate independently observed public-only Web acceptance evidence."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SUCCESS_CASES = ("static-html", "rendered-html", "public-zh-article", "rss-feed", "public-pdf")
FAILURE_CASES = ("timeout", "access-refused", "illegal-url")
PAIR_CASES = ("duplicate-url", "changed-content")
ALL_CASES = SUCCESS_CASES + PAIR_CASES + FAILURE_CASES
POLICY = {"public_only": True, "authenticated": False, "submitted_forms": False, "cookies_persisted": False}
REPO_ROOT = Path(__file__).resolve().parents[2]


def _load(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError("receipt must contain an object")
    return payload


def _source(path: Path) -> dict[str, Any]:
    payload = _load(path)
    if payload.get("schema_version") != "ds-lite.source-record.v2":
        raise ValueError("source evidence must be ds-lite.source-record.v2")
    if payload.get("policy") != POLICY:
        raise ValueError("source evidence is not public-only")
    if payload.get("status") not in {"captured", "failed"}:
        raise ValueError("source evidence must be captured or failed")
    return payload


def _failure(path: Path) -> dict[str, Any]:
    payload = _load(path)
    if payload.get("schema_version") != "ds-lite.web-failure-observation.v1":
        raise ValueError("failure evidence must be ds-lite.web-failure-observation.v1")
    if payload.get("status") != "observed" or payload.get("policy") != POLICY:
        raise ValueError("failure observation must be public-only and observed")
    if not isinstance(payload.get("failure_layer"), str) or not payload["failure_layer"]:
        raise ValueError("failure observation requires failure_layer")
    return payload


def _ref(path: Path) -> str:
    try:
        return path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        raise ValueError("evidence must remain inside the repository")


def _entry(path: Path, payload: dict[str, Any], status: str) -> dict[str, Any]:
    return {"status": status, "record_ref": _ref(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "schema_version": payload.get("schema_version", "not-observed")}


def evaluate(case_values: list[str], companion: str | None) -> tuple[dict[str, Any], int]:
    supplied: dict[str, list[Path]] = {}
    for value in case_values:
        try:
            case, raw_path = value.split("=", 1)
        except ValueError as exc:
            raise ValueError("case must use CASE=PATH") from exc
        if case not in ALL_CASES:
            raise ValueError(f"unsupported case: {case}")
        path = Path(raw_path).expanduser().resolve()
        supplied.setdefault(case, []).append(path)
    cases: dict[str, Any] = {}
    for case in SUCCESS_CASES:
        paths = supplied.get(case, [])
        if len(paths) != 1:
            cases[case] = {"status": "not-verified", "reason": "exactly one record is required"}
            continue
        payload = _source(paths[0])
        ok = payload["status"] == "captured"
        cases[case] = _entry(paths[0], payload, "passed" if ok else "blocked")
    for case in PAIR_CASES:
        paths = supplied.get(case, [])
        if len(paths) != 2:
            cases[case] = {"status": "not-verified", "reason": "exactly two records are required"}
            continue
        payloads = [_source(path) for path in paths]
        hashes = [str(item.get("content_sha256", "")) for item in payloads]
        captured = all(item["status"] == "captured" for item in payloads)
        relation = hashes[0] == hashes[1] if case == "duplicate-url" else hashes[0] != hashes[1]
        cases[case] = {"status": "passed" if captured and relation else "blocked", "record_refs": [_ref(path) for path in paths],
                       "sha256": [hashlib.sha256(path.read_bytes()).hexdigest() for path in paths]}
    for case in FAILURE_CASES:
        paths = supplied.get(case, [])
        if len(paths) != 1:
            cases[case] = {"status": "not-verified", "reason": "exactly one failure observation is required"}
            continue
        payload = _failure(paths[0]) if case == "illegal-url" else _source(paths[0])
        if case != "illegal-url" and payload["status"] != "failed":
            cases[case] = _entry(paths[0], payload, "blocked")
            continue
        cases[case] = _entry(paths[0], payload, "passed")
    adapter = {"status": "not-verified"}
    if companion:
        path = Path(companion).expanduser().resolve()
        payload = _source(path)
        valid = payload["status"] == "captured" and payload.get("backend_id") == "opencli-cli"
        adapter = _entry(path, payload, "passed" if valid else "blocked")
    passed = all(cases.get(case, {}).get("status") == "passed" for case in ALL_CASES) and adapter["status"] == "passed"
    result = {"schema_version": "ds-lite.web-benchmark-acceptance.v1", "status": "passed" if passed else "blocked",
              "failure_layer": "none" if passed else "web-benchmark-completeness", "observed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
              "case_count": len(ALL_CASES), "independent_case_records": sum(len(paths) for paths in supplied.values()),
              "cases": cases, "js_pdf_coverage": {"javascript": cases.get("rendered-html", {}).get("status"), "pdf": cases.get("public-pdf", {}).get("status")},
              "companion_adapter": adapter, "public_only": True, "authenticated": False, "cookies_persisted": False,
              "forms_submitted": False, "raw_output_persisted": False, "unverified": [case for case in ALL_CASES if cases.get(case, {}).get("status") != "passed"],
              "next_action": "formal release aggregation" if passed else "complete only the listed independent Web observations", "extensions": {}}
    return result, 0 if passed else 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Aggregate DS Lite public Web acceptance without evidence inference.")
    parser.add_argument("--case", action="append", default=[])
    parser.add_argument("--companion-adapter")
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    output = Path(args.output).expanduser().resolve()
    if output.exists():
        print(json.dumps({"status": "blocked", "reason": "output-exists"}))
        return 2
    try:
        result, code = evaluate(args.case, args.companion_adapter)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps({"status": result["status"]}, ensure_ascii=False))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
