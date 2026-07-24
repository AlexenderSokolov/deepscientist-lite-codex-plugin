#!/usr/bin/env python3
"""Read-only inventory and update planning for third-party project sources."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

SCHEMA = "ds-lite.upstream-audit.v1"
ID_RE = re.compile(r"^[a-z0-9][a-z0-9.-]+$")


class UpstreamError(RuntimeError):
    pass


def registry_path(repo_root: Path) -> Path:
    return repo_root / "plugins" / "deepscientist-lite" / "references" / "upstream-project-registry.json"


def load_registry(repo_root: Path) -> dict:
    try:
        value = json.loads(registry_path(repo_root).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise UpstreamError("upstream project registry is invalid") from exc
    if value.get("schema_version") != "ds-lite.upstream-project-registry.v1":
        raise UpstreamError("unsupported upstream project registry schema")
    projects = value.get("projects")
    if not isinstance(projects, list) or not projects:
        raise UpstreamError("upstream registry has no projects")
    for project in projects:
        if not isinstance(project, dict) or not ID_RE.fullmatch(str(project.get("id", ""))):
            raise UpstreamError("upstream registry contains an invalid project id")
    return value


def relative_ref(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return "external"


def fresh_write(path: Path, value: str) -> None:
    if path.exists():
        raise UpstreamError(f"refusing to overwrite existing output: {path.name}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8", newline="\n")


def verify_project(repo_root: Path, project: dict) -> dict:
    vendor = project.get("vendor_path")
    vendor_exists = bool(vendor) and (repo_root / PurePosixPath(vendor)).is_dir()
    license_observed = False
    if vendor_exists:
        license_observed = any((repo_root / PurePosixPath(vendor) / name).is_file() for name in ("LICENSE", "LICENSE.md", "LICENSE.txt", "package.json"))
    return {
        "id": project["id"],
        "pinned_commit_present": bool(project.get("pinned_commit")),
        "vendor_present": vendor_exists,
        "license_evidence_observed": license_observed,
        "disposition": project["disposition"],
        "status": "passed" if (not project.get("vendor_path") or (vendor_exists and license_observed)) else "blocked",
    }


def github_repo(repository: str) -> str:
    match = re.match(r"https://github\.com/([^/]+/[^/]+?)(?:\.git)?$", repository.rstrip("/"))
    if not match:
        raise UpstreamError("only GitHub repository URLs are supported by the read-only checker")
    return match.group(1)


def remote_commit(project: dict, timeout: int = 20) -> dict:
    pinned = project.get("pinned_commit", "")
    if not pinned:
        return {"remote_status": "not-observed", "reason": "no-pinned-commit"}
    url = f"https://api.github.com/repos/{github_repo(project['repository'])}/commits/{pinned}"
    request = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": "ds-lite-upstream-manager"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, urllib.error.HTTPError, UnicodeError, json.JSONDecodeError):
        return {"remote_status": "not-observed", "reason": "github-api-unavailable"}
    sha = payload.get("sha") if isinstance(payload, dict) else None
    if not isinstance(sha, str):
        return {"remote_status": "not-observed", "reason": "unexpected-response-shape"}
    return {"remote_status": "reachable", "pinned_commit_confirmed": sha.lower() == pinned.lower()}


def inventory(repo_root: Path) -> dict:
    registry = load_registry(repo_root)
    return {
        "schema_version": "ds-lite.upstream-inventory.v1",
        "project_count": len(registry["projects"]),
        "projects": [{"id": item["id"], "disposition": item["disposition"], "pinned_commit": bool(item.get("pinned_commit"))} for item in registry["projects"]],
    }


def audit(repo_root: Path, *, check_remote: bool) -> dict:
    registry = load_registry(repo_root)
    observations = []
    for project in registry["projects"]:
        item = verify_project(repo_root, project)
        if check_remote:
            item.update(remote_commit(project))
        observations.append(item)
    status = "passed" if all(item["status"] == "passed" for item in observations) else "blocked"
    return {
        "schema_version": SCHEMA,
        "checked_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "status": status,
        "remote_check": check_remote,
        "projects": observations,
        "raw_response_persisted": False,
        "secrets_persisted": False,
        "next_action": "review-generated-update-plan" if status == "passed" else "repair-or-audit-reported-projects",
    }


def update_plan(repo_root: Path, audit_value: dict) -> str:
    lines = [
        "# Upstream Update Plan",
        "",
        f"Generated: {audit_value['checked_at']}",
        "",
        "This is a read-only plan. It does not overwrite vendor sources, merge changes, or publish releases.",
        "",
        "| Project | Current state | Action |",
        "|---|---|---|",
    ]
    for project in audit_value["projects"]:
        if project.get("remote_status") == "reachable" and project.get("pinned_commit_confirmed") is False:
            action = "inspect upstream diff, update provenance, adapt tests, then request review"
        elif project["status"] != "passed":
            action = "repair vendor/license evidence before considering an update"
        else:
            action = "no update observed"
        lines.append(f"| `{project['id']}` | `{project['status']}` | {action} |")
    lines.extend(["", "Unverified items remain `not-observed`; no automatic source update is allowed.", ""])
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inventory and audit pinned third-party sources.")
    parser.add_argument("command", choices=("inventory", "check", "diff", "plan-update", "verify"))
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--output")
    args = parser.parse_args(argv)
    try:
        root = Path(args.repo_root).resolve()
        if args.command == "inventory":
            result = inventory(root)
        elif args.command == "verify":
            result = audit(root, check_remote=False)
        else:
            result = audit(root, check_remote=True)
            if args.command == "plan-update":
                content = update_plan(root, result)
                if not args.output:
                    raise UpstreamError("plan-update requires --output")
                fresh_write(Path(args.output), content)
                result = {"status": result["status"], "plan_written": relative_ref(Path(args.output), root), "raw_response_persisted": False}
        if args.output and args.command != "plan-update":
            fresh_write(Path(args.output), json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    except UpstreamError as exc:
        print(json.dumps({"status": "blocked", "failure_layer": "upstream-audit", "message": str(exc), "secrets_persisted": False}, ensure_ascii=True))
        return 1
    print(json.dumps(result, ensure_ascii=True))
    return 0 if result.get("status") in {"passed", "reachable"} or args.command == "inventory" else 1


if __name__ == "__main__":
    raise SystemExit(main())
