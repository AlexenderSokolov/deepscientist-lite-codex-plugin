#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from tools.validation.release_identity import ReleaseIdentityError, load_package_set
except ModuleNotFoundError:
    from release_identity import ReleaseIdentityError, load_package_set


SCHEMA = "ds-lite.academic-provider-acceptance.v1"
ALL_PROVIDERS = ("crossref", "openalex", "semantic-scholar", "arxiv")
TRANSIENT_FAILURES = {"timeout", "rate-limit", "network"}


class AcceptanceError(ValueError):
    pass


def _load_module(path: Path):
    spec = importlib.util.spec_from_file_location("ds_lite_citation_check_acceptance", path)
    if spec is None or spec.loader is None:
        raise AcceptanceError("citation-check-module-unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _manifest(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise AcceptanceError(f"manifest-unavailable:{path.parent.parent.name}") from exc
    if not isinstance(value, dict):
        raise AcceptanceError("manifest-must-be-object")
    return value


def _write_fresh(path: Path, payload: dict[str, Any]) -> None:
    resolved = path.expanduser().resolve()
    resolved.parent.mkdir(parents=True, exist_ok=True)
    try:
        with resolved.open("x", encoding="utf-8") as stream:
            stream.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    except FileExistsError as exc:
        raise AcceptanceError("output-already-exists") from exc


def _base(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA,
        "observed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "status": "blocked",
        "reason": "not-started",
        "evidence_stage": "preliminary",
        "candidate_bound": False,
        "candidate_digest": None,
        "sanitized": True,
        "host_acceptance_substitute": False,
        "authorized_external_provider": bool(args.authorized_external_provider),
        "network_attempted": False,
        "automatic_retry": False,
        "request_count": 0,
        "attempts_per_provider": {},
        "providers": args.provider or list(ALL_PROVIDERS),
        "provider_statuses": {},
        "overall_status": "pending",
        "submission_allowed": False,
        "citation_check": None,
        "unverified_items": ["live-provider-behavior"],
    }


def run(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    receipt = _base(args)
    if not args.authorized_external_provider:
        receipt["reason"] = "external-provider-authorization-required"
        return receipt, 2

    repo_root = Path(args.repo_root).expanduser().resolve()
    core_root = Path(args.core_root).expanduser().resolve() if args.core_root else repo_root / "plugins" / "deepscientist-lite-core"
    academic_root = repo_root / "plugins" / "deepscientist-lite-academic"
    try:
        packages = load_package_set(repo_root)["packages"]
        expected_core = {"name": packages["core"]["name"], "version": packages["core"]["version"]}
        expected_academic = {"name": packages["academic"]["name"], "version": packages["academic"]["version"]}
    except (ReleaseIdentityError, KeyError, TypeError):
        receipt["reason"] = "package-set-unavailable"
        return receipt, 2
    core = _manifest(core_root / ".codex-plugin" / "plugin.json")
    academic = _manifest(academic_root / ".codex-plugin" / "plugin.json")
    if {"name": core.get("name"), "version": core.get("version")} != expected_core:
        receipt["reason"] = "incompatible-core"
        return receipt, 2
    if {"name": academic.get("name"), "version": academic.get("version")} != expected_academic:
        receipt["reason"] = "incompatible-academic-pack"
        return receipt, 2

    citation = _load_module(academic_root / "scripts" / "ds_lite_citation_check.py")
    try:
        query = json.loads(Path(args.query).expanduser().resolve().read_text(encoding="utf-8"))
        providers = args.provider or list(ALL_PROVIDERS)
        receipt["network_attempted"] = True
        results = []
        for provider in providers:
            attempts = 0
            result: dict[str, Any] | None = None
            while attempts < args.max_attempts:
                attempts += 1
                try:
                    result = citation.query_provider(provider, query, timeout=args.timeout)
                except TimeoutError:
                    result = {
                        "provider": provider,
                        "status": "unavailable",
                        "identifier_match": "none",
                        "metadata_match": [],
                        "evidence_uri": "",
                        "failure_category": "timeout",
                    }
                except OSError:
                    result = {
                        "provider": provider,
                        "status": "unavailable",
                        "identifier_match": "none",
                        "metadata_match": [],
                        "evidence_uri": "",
                        "failure_category": "network",
                    }
                receipt["request_count"] += 1
                if (
                    result.get("status") != "unavailable"
                    or result.get("failure_category") not in TRANSIENT_FAILURES
                    or attempts >= args.max_attempts
                ):
                    break
                receipt["automatic_retry"] = True
                time.sleep(2 ** (attempts - 1))
            receipt["attempts_per_provider"][provider] = attempts
            assert result is not None
            results.append(result)
        check = citation.evaluate_check(
            query,
            results,
            mode="submission",
            reading_scope=args.reading_scope,
        )
    except (OSError, UnicodeError, json.JSONDecodeError, citation.CitationCheckError) as exc:
        receipt["reason"] = f"provider-check-error:{type(exc).__name__}"
        return receipt, 2

    receipt["provider_statuses"] = {item["provider"]: item["status"] for item in results}
    receipt["overall_status"] = check["overall_status"]
    receipt["submission_allowed"] = check["submission_allowed"]
    receipt["citation_check"] = check
    unavailable = [item["provider"] for item in results if item["status"] == "unavailable"]
    if unavailable:
        receipt["reason"] = "one-or-more-providers-unavailable"
        receipt["unverified_items"] = [f"provider:{name}" for name in unavailable]
        return receipt, 2
    if check["overall_status"] != "verified":
        receipt["reason"] = f"citation-{check['overall_status']}"
        receipt["unverified_items"] = ["citation-verification"]
        return receipt, 2
    receipt["status"] = "passed"
    receipt["reason"] = "authorized-live-providers-observed"
    receipt["unverified_items"] = []
    return receipt, 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run one authorized Academic live-provider acceptance.")
    parser.add_argument("--repo-root", default=str(Path(__file__).resolve().parents[2]))
    parser.add_argument("--core-root")
    parser.add_argument("--query", required=True, help="Path to a ds-lite citation query JSON object; not a free-text title")
    parser.add_argument("--output", required=True)
    parser.add_argument("--provider", action="append", choices=ALL_PROVIDERS)
    parser.add_argument("--reading-scope", choices=("metadata-only", "abstract", "full-text"), default="metadata-only")
    parser.add_argument("--timeout", type=float, default=15.0)
    parser.add_argument("--max-attempts", type=int, choices=(1, 2, 3), default=3)
    parser.add_argument("--authorized-external-provider", action="store_true")
    args = parser.parse_args(argv)
    try:
        receipt, code = run(args)
        _write_fresh(Path(args.output), receipt)
    except (OSError, UnicodeError, json.JSONDecodeError, AcceptanceError) as exc:
        print(json.dumps({"schema_version": SCHEMA, "status": "blocked", "reason": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps({"schema_version": SCHEMA, "status": receipt["status"], "reason": receipt["reason"]}, ensure_ascii=False))
    return code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
