#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import socket
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any


CHECK_SCHEMA = "ds-lite.citation-check.v1"
BATCH_SCHEMA = "ds-lite.citation-check-batch.v1"
PROVIDERS = {"crossref", "openalex", "semantic-scholar", "arxiv"}
PROVIDER_STATUSES = {"matched", "not-found", "unavailable", "not-applicable", "conflict"}
OVERALL_STATUSES = {"verified", "conflict", "not-found", "pending"}
READING_SCOPES = {"metadata-only", "abstract", "full-text"}
MODES = {"draft", "submission"}
METADATA_FIELDS = {"title", "authors", "year"}
FAILURE_CATEGORIES = {"none", "timeout", "rate-limit", "auth", "network", "http", "malformed"}
CACHE_TTL_DAYS = {"verified": 30, "conflict": 7, "not-found": 7}
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,191}$")


class CitationCheckError(ValueError):
    pass


def _utc(value: datetime | None = None) -> datetime:
    result = value or datetime.now(timezone.utc)
    if result.tzinfo is None:
        raise CitationCheckError("checked_at must be timezone-aware")
    return result.astimezone(timezone.utc)


def _timestamp(value: datetime | None = None) -> str:
    return _utc(value).isoformat().replace("+00:00", "Z")


def _parse_timestamp(value: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise CitationCheckError("timestamp must be UTC and end with Z")
    try:
        return datetime.fromisoformat(value.removesuffix("Z") + "+00:00")
    except ValueError as exc:
        raise CitationCheckError("timestamp is invalid") from exc


def _safe_ref(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise CitationCheckError(f"{label} must be a non-empty relative reference")
    posix = PurePosixPath(value.replace("\\", "/"))
    if posix.is_absolute() or PureWindowsPath(value).is_absolute() or ".." in posix.parts:
        raise CitationCheckError(f"{label} must be project-relative")
    return posix.as_posix()


def _validate_query(query: Any) -> dict[str, Any]:
    required = {"citation_id", "title", "authors", "year", "identifiers"}
    if not isinstance(query, dict) or set(query) != required:
        raise CitationCheckError("citation query fields are invalid")
    if not isinstance(query["citation_id"], str) or not ID_RE.fullmatch(query["citation_id"]):
        raise CitationCheckError("citation_id is invalid")
    if not isinstance(query["title"], str) or not query["title"].strip():
        raise CitationCheckError("title must be non-empty")
    if not isinstance(query["authors"], list) or not all(isinstance(item, str) and item.strip() for item in query["authors"]):
        raise CitationCheckError("authors must be a string list")
    if not isinstance(query["year"], int) or not 1000 <= query["year"] <= 3000:
        raise CitationCheckError("year is invalid")
    if not isinstance(query["identifiers"], dict):
        raise CitationCheckError("identifiers must be an object")
    allowed_ids = {"doi", "arxiv"}
    if not set(query["identifiers"]).issubset(allowed_ids):
        raise CitationCheckError("identifiers supports only doi and arxiv")
    if not all(isinstance(value, str) and value.strip() for value in query["identifiers"].values()):
        raise CitationCheckError("identifier values must be non-empty strings")
    return json.loads(json.dumps(query))


def _validate_provider(result: Any) -> dict[str, Any]:
    required = {"provider", "status", "identifier_match", "metadata_match", "evidence_uri", "failure_category"}
    if not isinstance(result, dict) or set(result) != required:
        raise CitationCheckError("provider result fields are invalid")
    if result["provider"] not in PROVIDERS:
        raise CitationCheckError("provider is unsupported")
    if result["status"] not in PROVIDER_STATUSES:
        raise CitationCheckError("provider status is invalid")
    if result["identifier_match"] not in {"exact", "different", "none"}:
        raise CitationCheckError("identifier_match is invalid")
    if not isinstance(result["metadata_match"], list) or not set(result["metadata_match"]).issubset(METADATA_FIELDS):
        raise CitationCheckError("metadata_match is invalid")
    if not isinstance(result["evidence_uri"], str) or (result["evidence_uri"] and not result["evidence_uri"].startswith(("https://", "http://"))):
        raise CitationCheckError("evidence_uri must be empty or HTTP(S)")
    if result["failure_category"] not in FAILURE_CATEGORIES:
        raise CitationCheckError("failure_category is invalid")
    if result["status"] == "unavailable" and result["failure_category"] == "none":
        raise CitationCheckError("unavailable provider requires a failure category")
    return json.loads(json.dumps(result))


def evaluate_check(
    query: dict[str, Any],
    provider_results: list[dict[str, Any]],
    *,
    mode: str = "draft",
    reading_scope: str = "metadata-only",
    claim_locations: list[dict[str, str]] | None = None,
    checked_at: datetime | None = None,
) -> dict[str, Any]:
    query = _validate_query(query)
    if mode not in MODES:
        raise CitationCheckError("mode is invalid")
    if reading_scope not in READING_SCOPES:
        raise CitationCheckError("reading_scope is invalid")
    providers = [_validate_provider(item) for item in provider_results]
    names = [item["provider"] for item in providers]
    if len(names) != len(set(names)):
        raise CitationCheckError("provider results must be independent and unique")
    locations = claim_locations or []
    for item in locations:
        if not isinstance(item, dict) or set(item) != {"claim_id", "page", "section"}:
            raise CitationCheckError("claim location fields are invalid")
        if not all(isinstance(value, str) for value in item.values()) or not item["claim_id"]:
            raise CitationCheckError("claim location values are invalid")

    if any(item["status"] == "conflict" or item["identifier_match"] == "different" for item in providers):
        overall = "conflict"
    elif any(item["status"] == "matched" and item["identifier_match"] == "exact" for item in providers):
        overall = "verified"
    else:
        corroborating = {
            item["provider"]
            for item in providers
            if item["status"] == "matched" and set(item["metadata_match"]) == METADATA_FIELDS
        }
        if len(corroborating) >= 2:
            overall = "verified"
        elif any(item["status"] == "unavailable" for item in providers) or not providers:
            overall = "pending"
        else:
            overall = "not-found"

    checked = _utc(checked_at)
    ttl = CACHE_TTL_DAYS.get(overall)
    result = {
        "schema_version": CHECK_SCHEMA,
        "citation": query,
        "mode": mode,
        "reading_scope": reading_scope,
        "claim_locations": locations,
        "providers": providers,
        "overall_status": overall,
        "submission_allowed": mode != "submission" or overall == "verified",
        "checked_at": _timestamp(checked),
        "cache_expires_at": _timestamp(checked + timedelta(days=ttl)) if ttl else "",
        "extensions": {},
    }
    return validate_check(result)


def validate_check(payload: Any) -> dict[str, Any]:
    required = {
        "schema_version", "citation", "mode", "reading_scope", "claim_locations", "providers",
        "overall_status", "submission_allowed", "checked_at", "cache_expires_at", "extensions",
    }
    if not isinstance(payload, dict) or set(payload) != required:
        raise CitationCheckError("citation check fields are invalid")
    if payload["schema_version"] != CHECK_SCHEMA:
        raise CitationCheckError("citation check schema is unsupported")
    _validate_query(payload["citation"])
    if payload["mode"] not in MODES or payload["reading_scope"] not in READING_SCOPES:
        raise CitationCheckError("mode or reading_scope is invalid")
    if not isinstance(payload["claim_locations"], list):
        raise CitationCheckError("claim_locations must be a list")
    for location in payload["claim_locations"]:
        if not isinstance(location, dict) or set(location) != {"claim_id", "page", "section"}:
            raise CitationCheckError("claim location fields are invalid")
    if not isinstance(payload["providers"], list):
        raise CitationCheckError("providers must be a list")
    for provider in payload["providers"]:
        _validate_provider(provider)
    if payload["overall_status"] not in OVERALL_STATUSES:
        raise CitationCheckError("overall_status is invalid")
    expected_allowed = payload["mode"] != "submission" or payload["overall_status"] == "verified"
    if payload["submission_allowed"] is not expected_allowed:
        raise CitationCheckError("submission_allowed contradicts mode and status")
    checked = _parse_timestamp(payload["checked_at"])
    ttl = CACHE_TTL_DAYS.get(payload["overall_status"])
    expected_expiry = _timestamp(checked + timedelta(days=ttl)) if ttl else ""
    if payload["cache_expires_at"] != expected_expiry:
        raise CitationCheckError("cache_expires_at contradicts status TTL")
    if not isinstance(payload["extensions"], dict):
        raise CitationCheckError("extensions must be an object")
    return json.loads(json.dumps(payload))


def build_batch(checks: list[dict[str, Any]]) -> dict[str, Any]:
    validated = [validate_check(item) for item in checks]
    summary = {status: 0 for status in ("verified", "conflict", "not-found", "pending")}
    for item in validated:
        summary[item["overall_status"]] += 1
    return {"schema_version": BATCH_SCHEMA, "checks": validated, "summary": summary, "extensions": {}}


def validate_batch(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict) or set(payload) != {"schema_version", "checks", "summary", "extensions"}:
        raise CitationCheckError("citation batch fields are invalid")
    if payload["schema_version"] != BATCH_SCHEMA or not isinstance(payload["checks"], list):
        raise CitationCheckError("citation batch schema is invalid")
    rebuilt = build_batch(payload["checks"])
    if payload["summary"] != rebuilt["summary"]:
        raise CitationCheckError("citation batch summary is inconsistent")
    if not isinstance(payload["extensions"], dict):
        raise CitationCheckError("extensions must be an object")
    return json.loads(json.dumps(payload))


def _cache_path(cache_root: Path, citation_id: str) -> Path:
    digest = hashlib.sha256(citation_id.encode("utf-8")).hexdigest()
    return cache_root / f"{digest}.json"


def write_cache(cache_root: Path, check: dict[str, Any]) -> bool:
    check = validate_check(check)
    if check["overall_status"] == "pending":
        return False
    root = cache_root.expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    path = _cache_path(root, check["citation"]["citation_id"])
    path.write_text(json.dumps(check, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return True


def read_cache(cache_root: Path, citation_id: str, *, now: datetime | None = None, force_refresh: bool = False) -> dict[str, Any] | None:
    if force_refresh:
        return None
    path = _cache_path(cache_root.expanduser().resolve(), citation_id)
    try:
        check = validate_check(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, UnicodeError, json.JSONDecodeError, CitationCheckError):
        return None
    if check["overall_status"] == "pending" or _utc(now) >= _parse_timestamp(check["cache_expires_at"]):
        return None
    return check


def _normalized_text(value: str) -> str:
    return " ".join(re.findall(r"[\w]+", value.casefold(), flags=re.UNICODE))


def _surname(value: str) -> str:
    parts = _normalized_text(value).split()
    return parts[-1] if parts else ""


def _compare_record(query: dict[str, Any], record: dict[str, Any], provider: str, evidence_uri: str) -> dict[str, Any]:
    query_ids = {key: value.casefold().removeprefix("https://doi.org/") for key, value in query["identifiers"].items()}
    record_ids = {key: str(value).casefold().removeprefix("https://doi.org/") for key, value in record.get("identifiers", {}).items() if value}
    shared = set(query_ids) & set(record_ids)
    identifier_match = "none"
    if shared:
        identifier_match = "exact" if all(query_ids[key] == record_ids[key] for key in shared) else "different"
    metadata: list[str] = []
    if _normalized_text(query["title"]) == _normalized_text(str(record.get("title", ""))):
        metadata.append("title")
    expected_surnames = {_surname(item) for item in query["authors"] if _surname(item)}
    observed_surnames = {_surname(str(item)) for item in record.get("authors", []) if _surname(str(item))}
    if expected_surnames and expected_surnames.issubset(observed_surnames):
        metadata.append("authors")
    if record.get("year") == query["year"]:
        metadata.append("year")
    conflict = identifier_match == "different"
    matched = identifier_match == "exact" or bool(metadata)
    return {
        "provider": provider,
        "status": "conflict" if conflict else ("matched" if matched else "not-found"),
        "identifier_match": identifier_match,
        "metadata_match": metadata,
        "evidence_uri": evidence_uri,
        "failure_category": "none",
    }


def _request(url: str, timeout: float) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "DeepScientist-Lite/0.7 citation-check"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def _provider_failure(provider: str, category: str, status: str = "unavailable") -> dict[str, Any]:
    return {
        "provider": provider, "status": status, "identifier_match": "none", "metadata_match": [],
        "evidence_uri": "", "failure_category": category,
    }


def _json_record(provider: str, query: dict[str, Any], data: Any) -> tuple[dict[str, Any] | None, str]:
    if provider == "crossref":
        message = data.get("message", {})
        items = message.get("items") if isinstance(message, dict) else None
        item = (items or [message])[0] if message else None
        if not item:
            return None, ""
        title = (item.get("title") or [""])[0]
        authors = [" ".join(filter(None, (a.get("given", ""), a.get("family", "")))) for a in item.get("author", [])]
        parts = (item.get("published-print") or item.get("published-online") or {}).get("date-parts", [[]])
        year = parts[0][0] if parts and parts[0] else None
        return {"title": title, "authors": authors, "year": year, "identifiers": {"doi": item.get("DOI", "")}}, item.get("URL", "")
    if provider == "openalex":
        item = data if data.get("id") else (data.get("results") or [None])[0]
        if not item:
            return None, ""
        authors = [entry.get("author", {}).get("display_name", "") for entry in item.get("authorships", [])]
        ids = item.get("ids", {})
        return {"title": item.get("display_name", ""), "authors": authors, "year": item.get("publication_year"), "identifiers": {"doi": ids.get("doi", "")}}, item.get("id", "")
    item = data if data.get("paperId") else (data.get("data") or [None])[0]
    if not item:
        return None, ""
    external = item.get("externalIds") or {}
    return {
        "title": item.get("title", ""), "authors": [a.get("name", "") for a in item.get("authors", [])],
        "year": item.get("year"), "identifiers": {"doi": external.get("DOI", ""), "arxiv": external.get("ArXiv", "")},
    }, item.get("url", "") or f"https://www.semanticscholar.org/paper/{item.get('paperId', '')}"


def query_provider(provider: str, query: dict[str, Any], *, timeout: float = 15.0) -> dict[str, Any]:
    query = _validate_query(query)
    if provider not in PROVIDERS:
        raise CitationCheckError("provider is unsupported")
    doi = query["identifiers"].get("doi", "")
    arxiv = query["identifiers"].get("arxiv", "")
    quoted_title = urllib.parse.quote(query["title"])
    if provider == "crossref":
        url = f"https://api.crossref.org/works/{urllib.parse.quote(doi)}" if doi else f"https://api.crossref.org/works?query.title={quoted_title}&rows=1"
    elif provider == "openalex":
        url = f"https://api.openalex.org/works/https://doi.org/{urllib.parse.quote(doi)}" if doi else f"https://api.openalex.org/works?search={quoted_title}&per-page=1"
    elif provider == "semantic-scholar":
        fields = "title,authors,year,externalIds,url"
        identifier = f"DOI:{doi}" if doi else (f"ARXIV:{arxiv}" if arxiv else "")
        url = f"https://api.semanticscholar.org/graph/v1/paper/{urllib.parse.quote(identifier, safe=':')}?fields={fields}" if identifier else f"https://api.semanticscholar.org/graph/v1/paper/search?query={quoted_title}&limit=1&fields={fields}"
    else:
        if not arxiv and not query["title"]:
            return _provider_failure(provider, "none", "not-applicable")
        term = f"id:{arxiv}" if arxiv else f'ti:"{query["title"]}"'
        url = f"https://export.arxiv.org/api/query?search_query={urllib.parse.quote(term)}&max_results=1"
    try:
        raw = _request(url, timeout)
        if provider == "arxiv":
            root = ET.fromstring(raw)
            ns = {"a": "http://www.w3.org/2005/Atom"}
            entry = root.find("a:entry", ns)
            if entry is None:
                return _provider_failure(provider, "none", "not-found")
            identifier = entry.findtext("a:id", "", ns).rsplit("/", 1)[-1].split("v", 1)[0]
            record = {
                "title": entry.findtext("a:title", "", ns),
                "authors": [node.findtext("a:name", "", ns) for node in entry.findall("a:author", ns)],
                "year": int(entry.findtext("a:published", "0000", ns)[:4]),
                "identifiers": {"arxiv": identifier},
            }
            return _compare_record(query, record, provider, entry.findtext("a:id", "", ns))
        data = json.loads(raw.decode("utf-8"))
        record, evidence_uri = _json_record(provider, query, data)
        return _provider_failure(provider, "none", "not-found") if record is None else _compare_record(query, record, provider, evidence_uri)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return _provider_failure(provider, "none", "not-found")
        return _provider_failure(provider, "rate-limit" if exc.code == 429 else ("auth" if exc.code in {401, 403} else "http"))
    except (TimeoutError, socket.timeout):
        return _provider_failure(provider, "timeout")
    except urllib.error.URLError:
        return _provider_failure(provider, "network")
    except (UnicodeError, json.JSONDecodeError, ET.ParseError, KeyError, TypeError, ValueError):
        return _provider_failure(provider, "malformed")


def _write_fresh(path: Path, payload: Any) -> None:
    resolved = path.expanduser().resolve()
    package_root = Path(__file__).resolve().parents[1]
    if resolved == package_root or package_root in resolved.parents:
        raise CitationCheckError("outputs must remain outside the installed plugin")
    if resolved.exists():
        raise CitationCheckError("output already exists; refusing overwrite")
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate or execute DS Lite citation checks.")
    sub = parser.add_subparsers(dest="command", required=True)
    validate_parser = sub.add_parser("validate")
    validate_parser.add_argument("--path", required=True)
    live = sub.add_parser("check-live")
    live.add_argument("--query", required=True)
    live.add_argument("--output", required=True)
    live.add_argument("--provider", action="append", choices=sorted(PROVIDERS))
    live.add_argument("--mode", choices=sorted(MODES), default="draft")
    live.add_argument("--reading-scope", choices=sorted(READING_SCOPES), default="metadata-only")
    live.add_argument("--timeout", type=float, default=15.0)
    args = parser.parse_args(argv)
    try:
        if args.command == "validate":
            payload = json.loads(Path(args.path).read_text(encoding="utf-8"))
            validated = validate_batch(payload) if payload.get("schema_version") == BATCH_SCHEMA else validate_check(payload)
            result = {"status": "passed", "schema_version": validated["schema_version"]}
        else:
            query = json.loads(Path(args.query).read_text(encoding="utf-8"))
            selected = args.provider or sorted(PROVIDERS)
            providers = [query_provider(provider, query, timeout=args.timeout) for provider in selected]
            check = evaluate_check(query, providers, mode=args.mode, reading_scope=args.reading_scope)
            _write_fresh(Path(args.output), check)
            result = {"status": "passed", "overall_status": check["overall_status"], "submission_allowed": check["submission_allowed"]}
    except (OSError, UnicodeError, json.JSONDecodeError, CitationCheckError) as exc:
        print(json.dumps({"status": "blocked", "error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
