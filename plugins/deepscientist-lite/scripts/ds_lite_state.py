#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import stat
import sys
import time
import uuid
from collections import deque
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath, PureWindowsPath
from string import Template
from typing import Any, Callable, Iterator

import ds_lite_evidence
import ds_lite_protocol

SCHEMA_V1 = "ds-lite.graph.v1"
SCHEMA_VERSION = "ds-lite.graph.v2"
NODE_KINDS = {
    "intake",
    "scout",
    "idea",
    "experiment",
    "review",
    "analysis",
    "write",
    "decision",
    "finalize",
}
NODE_STATUSES = {"proposed", "active", "blocked", "done", "superseded", "abandoned"}
EDGE_RELATIONS = {"next", "branch", "supports", "blocks", "supersedes", "rollback"}
PROGRESSION_RELATIONS = {"next", "branch", "supersedes"}
FORBIDDEN_NODE_KEYS = {"thought", "chain_of_thought", "hidden_thought", "reasoning_trace"}
REQUIRED_NODE_FIELDS = {
    "id",
    "kind",
    "status",
    "title",
    "summary",
    "artifact_paths",
    "memory_paths",
    "evidence_paths",
    "created_at",
    "updated_at",
}
PATH_FIELDS = ("artifact_paths", "memory_paths", "evidence_paths")
EXTERNAL_URI_RE = re.compile(r"^external://([a-z][a-z0-9_-]*)/(.+)$")
MAP_REVISION_RE = re.compile(r"^- Revision: `([0-9]+)`$", re.MULTILINE)
LOCK_TIMEOUT_SECONDS = float(os.environ.get("DS_LITE_LOCK_TIMEOUT", "10"))
EVIDENCE_SCHEMA = "ds-lite.evidence.v1"
WORK_UNIT_RELATIVE = "research/work-unit.json"
RESERVED_PROFILES = {
    "literature-evidence",
    "mathematical-exploration",
    "software-evaluation",
    "numerical-simulation",
}
READINESS_RULES = [
    "artifact != progress",
    "ready != done",
    "idea != experiment",
    "metric wrong == protocol failure",
    "no visible loop == no agent experience",
]


def configure_text_streams() -> None:
    """Keep CLI output representable on Windows consoles with legacy code pages."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(errors="backslashreplace")
        except (AttributeError, OSError):
            pass


class CliError(Exception):
    def __init__(self, message: str, code: int = 1, details: list[str] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.details = details or []


class MigrationRequired(CliError):
    def __init__(self, paths: list[str]) -> None:
        super().__init__(
            "Graph v1 contains project-external absolute paths; provide --external-map alias=ROOT.",
            code=5,
            details=sorted(set(paths)),
        )


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def timestamp_slug() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def slugify(value: str, fallback: str = "node") -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    return slug or fallback


def state_path(root: Path) -> Path:
    return root / "research" / "state" / "graph.json"


def lock_path(root: Path) -> Path:
    return root / "research" / "state" / "graph.lock"


def template_root() -> Path:
    return Path(__file__).resolve().parents[1] / "assets" / "templates"


def ensure_dirs(root: Path) -> None:
    for item in ("research/state", "research/memory", "research/artifacts", "research/evidence"):
        (root / item).mkdir(parents=True, exist_ok=True)


def emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def read_optional_text(path_value: str) -> str:
    if not path_value:
        return ""
    return Path(path_value).read_text(encoding="utf-8").strip()


def value_or_file(value: str, file_value: str, label: str, required: bool = False) -> str:
    result = read_optional_text(file_value) or value
    if required and not result.strip():
        raise CliError(f"{label} is required; pass the value directly or use --{label}-file.")
    return result.strip()


def load_template(relative_path: str) -> Template:
    path = template_root() / relative_path
    if not path.exists():
        raise CliError(f"Required template not found: {path}")
    return Template(path.read_text(encoding="utf-8"))


def render_template(relative_path: str, values: dict[str, str]) -> str:
    try:
        return load_template(relative_path).substitute(values)
    except (KeyError, ValueError) as exc:
        raise CliError(f"Template rendering failed for {relative_path}: {exc}") from exc


def write_if_missing(path: Path, content: str) -> bool:
    if path.exists():
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return True


def atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    with temporary.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)
    if os.name != "nt":
        try:
            directory_fd = os.open(path.parent, os.O_RDONLY)
        except OSError:
            return
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)


@contextmanager
def graph_lock(root: Path, timeout: float = LOCK_TIMEOUT_SECONDS) -> Iterator[None]:
    ensure_dirs(root)
    path = lock_path(root)
    handle = path.open("a+b")
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
                    raise CliError(f"Timed out waiting for graph lock: {path}", code=3)
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


def load_graph(root: Path) -> dict[str, Any]:
    path = state_path(root)
    if not path.exists():
        raise CliError(f"State graph not found: {path}")
    try:
        graph = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CliError(f"Invalid JSON in {path}: {exc}") from exc
    if not isinstance(graph, dict):
        raise CliError(f"State graph must contain a JSON object: {path}")
    return graph


def save_graph(root: Path, graph: dict[str, Any]) -> None:
    atomic_write_text(state_path(root), json.dumps(graph, ensure_ascii=False, indent=2) + "\n")


def parse_external_maps(values: list[str]) -> dict[str, Path]:
    mappings: dict[str, Path] = {}
    for value in values:
        if "=" not in value:
            raise CliError(f"Invalid external map {value!r}; expected alias=ROOT.")
        alias, raw_root = value.split("=", 1)
        if not re.fullmatch(r"[a-z][a-z0-9_-]*", alias):
            raise CliError(f"Invalid external alias: {alias}")
        path = Path(raw_root).expanduser().resolve()
        if not path.is_absolute():
            raise CliError(f"External map root must be absolute: {raw_root}")
        mappings[alias] = path
    return mappings


def _validate_relative_parts(raw: str) -> str:
    posix = PurePosixPath(raw.replace("\\", "/"))
    if posix.is_absolute() or not posix.parts or any(part in {"", ".", ".."} for part in posix.parts):
        raise CliError(f"Path must be a normalized relative path without '..': {raw}")
    return posix.as_posix()


def normalize_graph_path(
    root: Path,
    value: str | None,
    external_maps: dict[str, Path] | None = None,
    migration: bool = False,
) -> str:
    raw = (value or "").strip()
    if not raw:
        return ""
    external_match = EXTERNAL_URI_RE.fullmatch(raw.replace("\\", "/"))
    if external_match:
        alias, remainder = external_match.groups()
        return f"external://{alias}/{_validate_relative_parts(remainder)}"

    path = Path(raw).expanduser()
    windows_absolute = PureWindowsPath(raw).is_absolute()
    if path.is_absolute() or windows_absolute:
        if windows_absolute and not path.is_absolute():
            if migration:
                raise MigrationRequired([raw])
            raise CliError(f"Project-external absolute path is forbidden; use external://alias/path: {raw}")
        resolved = path.resolve()
        try:
            return resolved.relative_to(root.resolve()).as_posix()
        except ValueError:
            for alias, mapped_root in (external_maps or {}).items():
                try:
                    relative = resolved.relative_to(mapped_root)
                except ValueError:
                    continue
                return f"external://{alias}/{_validate_relative_parts(relative.as_posix())}"
            if migration:
                raise MigrationRequired([raw])
            raise CliError(f"Project-external absolute path is forbidden; use external://alias/path: {raw}")
    return _validate_relative_parts(raw)


def resolve_graph_path(root: Path, value: str) -> tuple[Path | None, str | None]:
    match = EXTERNAL_URI_RE.fullmatch(value)
    if not match:
        return root / value, None
    alias, remainder = match.groups()
    env_name = "DS_LITE_EXTERNAL_" + re.sub(r"[^A-Z0-9]", "_", alias.upper())
    mapped = os.environ.get(env_name, "").strip()
    if not mapped:
        return None, f"{env_name} is not set"
    mapped_path = Path(mapped).expanduser()
    if not mapped_path.is_absolute():
        return None, f"{env_name} must contain an absolute path"
    return mapped_path.resolve() / PurePosixPath(remainder), None


def require_node(graph: dict[str, Any], node_id: str) -> dict[str, Any]:
    node = graph.get("nodes", {}).get(node_id)
    if not node:
        raise CliError(f"Unknown node id: {node_id}")
    return node


def make_node_id(graph: dict[str, Any], kind: str, title: str) -> str:
    base = f"{kind}-{slugify(title, fallback='node')}"
    node_id = base
    counter = 2
    while node_id in graph.get("nodes", {}):
        node_id = f"{base}-{counter}"
        counter += 1
    return node_id


def append_unique(items: list[str], value: str) -> None:
    if value and value not in items:
        items.append(value)


def add_edge_obj(
    graph: dict[str, Any],
    source: str,
    target: str,
    relation: str,
    reason: str = "",
    artifact_path: str = "",
) -> bool:
    if relation not in EDGE_RELATIONS:
        raise CliError(f"Invalid edge relation: {relation}")
    require_node(graph, source)
    require_node(graph, target)
    graph.setdefault("adjacency", {}).setdefault(source, [])
    for existing in graph["adjacency"][source]:
        if existing.get("to") == target and existing.get("relation") == relation:
            return False
    graph["adjacency"][source].append(
        {"to": target, "relation": relation, "reason": reason, "artifact_path": artifact_path}
    )
    return True


def parse_utc(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def monotonic_node_timestamp(node: dict[str, Any], candidate: str | None = None) -> str:
    timestamp = candidate or utc_now()
    parsed_candidate = parse_utc(timestamp)
    if parsed_candidate is None:
        return timestamp
    floor: tuple[datetime, str] | None = None
    for field in ("created_at", "updated_at"):
        value = node.get(field)
        parsed = parse_utc(value)
        if parsed is not None and (floor is None or parsed > floor[0]):
            floor = (parsed, value)
    if floor is not None and parsed_candidate < floor[0]:
        return floor[1]
    return timestamp


def find_route(graph: dict[str, Any], start: str, target: str, mode: str = "progression") -> list[str]:
    if not start or not target:
        return []
    if start == target:
        return [start]
    allowed = PROGRESSION_RELATIONS if mode == "progression" else EDGE_RELATIONS
    adjacency = graph.get("adjacency", {})
    seen = {start}
    queue: deque[tuple[str, list[str]]] = deque([(start, [start])])
    while queue:
        node_id, path = queue.popleft()
        for edge in adjacency.get(node_id, []):
            if edge.get("relation") not in allowed:
                continue
            child = edge.get("to")
            if not child or child in seen:
                continue
            if child == target:
                return path + [child]
            seen.add(child)
            queue.append((child, path + [child]))
    return []


def progression_cycle(graph: dict[str, Any]) -> list[str]:
    adjacency = graph.get("adjacency", {})
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node_id: str, trail: list[str]) -> list[str]:
        if node_id in visiting:
            start = trail.index(node_id) if node_id in trail else 0
            return trail[start:] + [node_id]
        if node_id in visited:
            return []
        visiting.add(node_id)
        for edge in adjacency.get(node_id, []):
            if edge.get("relation") not in PROGRESSION_RELATIONS:
                continue
            cycle = visit(str(edge.get("to", "")), trail + [node_id])
            if cycle:
                return cycle
        visiting.remove(node_id)
        visited.add(node_id)
        return []

    for node_id in graph.get("nodes", {}):
        cycle = visit(node_id, [])
        if cycle:
            return cycle
    return []


def evidence_manifest_paths(node: dict[str, Any]) -> list[str]:
    return [
        value
        for value in node.get("evidence_paths", [])
        if isinstance(value, str) and value.startswith("research/evidence/") and value.endswith("/manifest.json")
    ]


def validate_evidence_manifest(root: Path, node_id: str, node: dict[str, Any], path_value: str) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    resolved, problem = resolve_graph_path(root, path_value)
    if problem:
        warnings.append(f"node {node_id} evidence manifest cannot be resolved: {problem}")
        return errors, warnings
    if resolved is None or not resolved.exists():
        return errors, warnings
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        errors.append(f"node {node_id} evidence manifest is invalid JSON: {path_value}: {exc}")
        return errors, warnings
    if not isinstance(payload, dict) or payload.get("schema_version") != EVIDENCE_SCHEMA:
        errors.append(f"node {node_id} evidence manifest must use {EVIDENCE_SCHEMA}: {path_value}")
        return errors, warnings
    if payload.get("node_id") != node_id:
        errors.append(f"node {node_id} evidence manifest references node {payload.get('node_id')}: {path_value}")
    if payload.get("status") not in {"planned", "completed", "failed"}:
        errors.append(f"node {node_id} evidence manifest has invalid status: {path_value}")
    verification = payload.get("verification")
    verification_status = verification.get("status") if isinstance(verification, dict) else ""
    if verification_status not in {"pass", "warning", "fail", "not-run"}:
        errors.append(f"node {node_id} evidence manifest has invalid verification status: {path_value}")
    elif verification_status in {"not-run", "warning"}:
        warnings.append(f"node {node_id} evidence manifest is not strictly verified: {path_value}")
    elif verification_status == "fail":
        message = f"node {node_id} evidence manifest verification failed: {path_value}"
        if node.get("status") == "done":
            errors.append(message)
        else:
            warnings.append(message)
    return errors, warnings


def validate_graph(
    root: Path,
    graph: dict[str, Any],
    check_paths: bool = True,
    warning_nodes: list[str | None] | None = None,
) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    def warn(message: str, node_id: str | None = None) -> None:
        warnings.append(message)
        if warning_nodes is not None:
            warning_nodes.append(node_id)

    schema = graph.get("schema_version")
    if schema not in {SCHEMA_V1, SCHEMA_VERSION}:
        errors.append(f"schema_version must be {SCHEMA_V1} or {SCHEMA_VERSION}")
    if schema == SCHEMA_V1:
        warn("graph uses ds-lite.graph.v1; migrate before the next state change")
    if schema == SCHEMA_VERSION:
        revision = graph.get("revision")
        if not isinstance(revision, int) or revision < 0:
            errors.append("revision must be a non-negative integer")

    project = graph.get("project")
    if not isinstance(project, dict):
        errors.append("project must be an object")
    else:
        if not str(project.get("id", "")).strip():
            errors.append("project.id must not be empty")
        if not str(project.get("title", "")).strip():
            errors.append("project.title must not be empty")

    nodes = graph.get("nodes")
    adjacency = graph.get("adjacency")
    if not isinstance(nodes, dict):
        errors.append("nodes must be an object")
        nodes = {}
    if not isinstance(adjacency, dict):
        errors.append("adjacency must be an object")
        adjacency = {}

    active_nodes: list[str] = []
    for node_id, node in nodes.items():
        if not isinstance(node, dict):
            errors.append(f"node {node_id} must be an object")
            continue
        missing = REQUIRED_NODE_FIELDS - set(node)
        if missing:
            errors.append(f"node {node_id} missing fields: {', '.join(sorted(missing))}")
        forbidden = FORBIDDEN_NODE_KEYS & set(node)
        if forbidden:
            errors.append(f"node {node_id} contains forbidden hidden-reasoning fields: {', '.join(sorted(forbidden))}")
        if node.get("id") != node_id:
            errors.append(f"node key {node_id} does not match node.id {node.get('id')}")
        if node.get("kind") not in NODE_KINDS:
            errors.append(f"node {node_id} has invalid kind {node.get('kind')}")
        if node.get("status") not in NODE_STATUSES:
            errors.append(f"node {node_id} has invalid status {node.get('status')}")
        if node.get("status") == "active":
            active_nodes.append(node_id)
        created = parse_utc(node.get("created_at"))
        updated = parse_utc(node.get("updated_at"))
        if created is None:
            errors.append(f"node {node_id} has invalid created_at")
        if updated is None:
            errors.append(f"node {node_id} has invalid updated_at")
        if created and updated and updated < created:
            errors.append(f"node {node_id} updated_at precedes created_at")
        for list_field in PATH_FIELDS:
            values = node.get(list_field)
            if not isinstance(values, list):
                errors.append(f"node {node_id} field {list_field} must be a list")
                continue
            if len(values) != len(set(values)):
                errors.append(f"node {node_id} field {list_field} contains duplicate paths")
            for value in values:
                try:
                    normalized = normalize_graph_path(root, value)
                except CliError as exc:
                    errors.append(f"node {node_id} has invalid {list_field} path {value!r}: {exc}")
                    continue
                if normalized != value:
                    errors.append(f"node {node_id} path is not normalized: {value!r}")
                if not check_paths:
                    continue
                resolved, path_problem = resolve_graph_path(root, value)
                if path_problem:
                    warn(f"node {node_id} external path cannot be resolved: {path_problem}", node_id)
                    continue
                if resolved is not None and not resolved.exists():
                    message = f"node {node_id} {list_field} path does not exist: {value}"
                    if list_field in {"artifact_paths", "memory_paths"} or node.get("status") == "done":
                        errors.append(message)
                    else:
                        warn(message, node_id)

        if node.get("kind") == "experiment":
            manifests = evidence_manifest_paths(node)
            if not manifests:
                warn(f"experiment node {node_id} has no Evidence Pack manifest", node_id)
            for manifest_value in manifests:
                manifest_errors, manifest_warnings = validate_evidence_manifest(root, node_id, node, manifest_value)
                errors.extend(manifest_errors)
                for manifest_warning in manifest_warnings:
                    warn(manifest_warning, node_id)
        if node.get("kind") == "review":
            if not node.get("artifact_paths"):
                warn(f"review node {node_id} has no review artifact", node_id)
            if not evidence_manifest_paths(node):
                warn(f"review node {node_id} is not linked to an Evidence Pack manifest", node_id)

    if len(active_nodes) > 1:
        errors.append(f"multiple nodes have active status: {', '.join(sorted(active_nodes))}")
    root_id = graph.get("root_node_id", "")
    active_id = graph.get("active_node_id", "")
    if root_id not in nodes:
        errors.append(f"root_node_id references missing node {root_id}")
    if active_id:
        if active_id not in nodes:
            errors.append(f"active_node_id references missing node {active_id}")
        elif nodes[active_id].get("status") != "active":
            errors.append(f"active_node_id {active_id} does not have active status")
    if active_nodes and active_id not in active_nodes:
        errors.append("active_node_id does not match the node with active status")

    semantic_edges: set[tuple[str, str, str]] = set()
    progression_parents: dict[str, set[str]] = {node_id: set() for node_id in nodes}
    for source, edges in adjacency.items():
        if source not in nodes:
            errors.append(f"adjacency source {source} is not a node")
        if not isinstance(edges, list):
            errors.append(f"adjacency for {source} must be a list")
            continue
        for index, edge in enumerate(edges):
            if not isinstance(edge, dict):
                errors.append(f"edge {source}[{index}] must be an object")
                continue
            target = edge.get("to")
            relation = edge.get("relation")
            if target not in nodes:
                errors.append(f"edge {source}[{index}] points to missing node {target}")
            if relation not in EDGE_RELATIONS:
                errors.append(f"edge {source}[{index}] has invalid relation {relation}")
            edge_key = (source, str(target), str(relation))
            if edge_key in semantic_edges:
                errors.append(f"duplicate semantic edge: {source} -[{relation}]-> {target}")
            semantic_edges.add(edge_key)
            if relation in PROGRESSION_RELATIONS and target in progression_parents:
                progression_parents[target].add(source)
            for field in ("reason", "artifact_path"):
                if field not in edge:
                    errors.append(f"edge {source}[{index}] missing {field}")
            artifact_path = edge.get("artifact_path", "")
            if artifact_path:
                try:
                    normalized = normalize_graph_path(root, artifact_path)
                except CliError as exc:
                    errors.append(f"edge {source}[{index}] has invalid artifact_path: {exc}")
                    continue
                if normalized != artifact_path:
                    errors.append(f"edge {source}[{index}] artifact_path is not normalized")
                if check_paths:
                    resolved, path_problem = resolve_graph_path(root, artifact_path)
                    if path_problem:
                        warn(f"edge {source}[{index}] external path cannot be resolved: {path_problem}", source)
                    elif resolved is not None and not resolved.exists():
                        errors.append(f"edge {source}[{index}] artifact_path does not exist: {artifact_path}")

    for node_id in nodes:
        if node_id == root_id:
            continue
        if not find_route(graph, root_id, node_id, mode="progression"):
            errors.append(f"node {node_id} is unreachable from root through progression edges")
        node = nodes.get(node_id, {})
        if node.get("kind") in {"analysis", "write"}:
            parents = progression_parents.get(node_id, set())
            if not any(nodes.get(parent, {}).get("kind") == "review" for parent in parents):
                warn(f"{node.get('kind')} node {node_id} has no direct progression parent of kind review", node_id)
    cycle = progression_cycle(graph)
    if cycle:
        errors.append("progression graph contains a cycle: " + " -> ".join(cycle))
    return errors, warnings


def migration_preview(root: Path, graph: dict[str, Any], external_maps: dict[str, Path]) -> dict[str, Any]:
    if graph.get("schema_version") == SCHEMA_VERSION:
        return json.loads(json.dumps(graph))
    if graph.get("schema_version") != SCHEMA_V1:
        raise CliError(f"Cannot migrate unsupported schema: {graph.get('schema_version')}")
    migrated = json.loads(json.dumps(graph))
    unresolved: list[str] = []
    for node in migrated.get("nodes", {}).values():
        for field in PATH_FIELDS:
            normalized: list[str] = []
            for value in node.get(field, []):
                try:
                    normalized.append(normalize_graph_path(root, value, external_maps, migration=True))
                except MigrationRequired as exc:
                    unresolved.extend(exc.details)
            node[field] = normalized
    for edges in migrated.get("adjacency", {}).values():
        for edge in edges:
            value = edge.get("artifact_path", "")
            if not value:
                continue
            try:
                edge["artifact_path"] = normalize_graph_path(root, value, external_maps, migration=True)
            except MigrationRequired as exc:
                unresolved.extend(exc.details)
    if unresolved:
        raise MigrationRequired(unresolved)
    migrated["schema_version"] = SCHEMA_VERSION
    migrated["revision"] = 0
    return migrated


def backup_v1_graph(root: Path) -> Path:
    source = state_path(root)
    backup = source.with_name(f"graph.v1.{timestamp_slug()}.json")
    counter = 2
    while backup.exists():
        backup = source.with_name(f"graph.v1.{timestamp_slug()}.{counter}.json")
        counter += 1
    shutil.copy2(source, backup)
    try:
        backup.chmod(stat.S_IREAD)
    except OSError:
        pass
    return backup


def prepare_graph_for_write(
    root: Path,
    graph: dict[str, Any],
    external_maps: dict[str, Path] | None = None,
    create_backup: bool = True,
) -> tuple[dict[str, Any], Path | None]:
    if graph.get("schema_version") == SCHEMA_VERSION:
        return graph, None
    migrated = migration_preview(root, graph, external_maps or {})
    backup = backup_v1_graph(root) if create_backup else None
    return migrated, backup


def expected_revision(args: argparse.Namespace, graph: dict[str, Any]) -> None:
    expected = getattr(args, "expected_revision", None)
    if expected is not None and graph.get("revision", 0) != expected:
        raise CliError(
            f"Revision conflict: expected {expected}, found {graph.get('revision', 0)}.",
            code=4,
        )


def mutation_transaction(
    root: Path,
    args: argparse.Namespace,
    mutate: Callable[[dict[str, Any]], dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any], Path | None]:
    with graph_lock(root):
        graph = load_graph(root)
        was_v1 = graph.get("schema_version") == SCHEMA_V1
        graph, backup = prepare_graph_for_write(root, graph, create_backup=False)
        expected_revision(args, graph)
        payload = mutate(graph)
        graph["revision"] = int(graph.get("revision", 0)) + 1
        errors, _warnings = validate_graph(root, graph, check_paths=False)
        if errors:
            raise CliError("Mutation would create an invalid graph.", details=errors)
        if was_v1:
            backup = backup_v1_graph(root)
        save_graph(root, graph)
        if getattr(args, "render", True):
            render_map(root, graph)
        return graph, payload, backup


def markdown_escape(value: Any) -> str:
    return str(value or "").replace("|", "\\|").replace("\n", " ")


def mermaid_id(node_id: str) -> str:
    return "n_" + re.sub(r"[^a-zA-Z0-9_]", "_", node_id)


def render_map(root: Path, graph: dict[str, Any]) -> Path:
    project = graph.get("project", {})
    nodes = graph.get("nodes", {})
    adjacency = graph.get("adjacency", {})
    active = graph.get("active_node_id", "")
    root_id = graph.get("root_node_id", "")
    route = find_route(graph, root_id, active, mode="progression") if active else []

    active_lines = []
    if route:
        for node_id in route:
            node = nodes.get(node_id, {})
            active_lines.append(
                f"- `{node_id}` - {node.get('kind', '')}: {node.get('title', '')} [{node.get('status', '')}]"
            )
    else:
        active_lines.append("- No progression route found from root to active node.")

    graph_lines = ["```mermaid", "graph TD"]
    if not nodes:
        graph_lines.append('  empty["No nodes"]')
    for node_id, node in nodes.items():
        label = f"{node.get('kind', '')}: {node.get('title', '')} ({node.get('status', '')})".replace('"', "'")
        graph_lines.append(f'  {mermaid_id(node_id)}["{label}"]')
    for source, edges in adjacency.items():
        for edge in edges:
            target = edge.get("to", "")
            if source in nodes and target in nodes:
                graph_lines.append(
                    f"  {mermaid_id(source)} -->|{edge.get('relation', '')}| {mermaid_id(target)}"
                )
    graph_lines.append("```")

    node_lines = ["| id | kind | status | title | artifacts |", "| --- | --- | --- | --- | --- |"]
    for node_id, node in nodes.items():
        node_lines.append(
            f"| `{markdown_escape(node_id)}` | {markdown_escape(node.get('kind'))} | "
            f"{markdown_escape(node.get('status'))} | {markdown_escape(node.get('title'))} | "
            f"{markdown_escape(', '.join(node.get('artifact_paths', [])))} |"
        )
    edge_lines = [
        "| from | relation | to | reason | artifact |",
        "| --- | --- | --- | --- | --- |",
    ]
    for source, edges in adjacency.items():
        for edge in edges:
            edge_lines.append(
                f"| `{markdown_escape(source)}` | {markdown_escape(edge.get('relation'))} | "
                f"`{markdown_escape(edge.get('to'))}` | {markdown_escape(edge.get('reason'))} | "
                f"{markdown_escape(edge.get('artifact_path'))} |"
            )

    content = render_template(
        "RESEARCH_MAP.md",
        {
            "project_title": str(project.get("title") or project.get("id") or "Untitled Project"),
            "schema_version": str(graph.get("schema_version", "")),
            "revision": str(graph.get("revision", 0)),
            "project_id": str(project.get("id", "")),
            "root_node_id": str(root_id),
            "active_node_id": str(active),
            "rendered_at": utc_now(),
            "active_route": "\n".join(active_lines),
            "mermaid_graph": "\n".join(graph_lines),
            "node_table": "\n".join(node_lines),
            "edge_table": "\n".join(edge_lines),
        },
    )
    output = root / "RESEARCH_MAP.md"
    atomic_write_text(output, content.rstrip() + "\n")
    return output


def short_node(node: dict[str, Any] | None) -> dict[str, Any]:
    node = node or {}
    return {
        "id": node.get("id", ""),
        "kind": node.get("kind", ""),
        "status": node.get("status", ""),
        "title": node.get("title", ""),
        "summary": node.get("summary", ""),
        "artifact_paths": list(node.get("artifact_paths", [])),
        "evidence_paths": list(node.get("evidence_paths", [])),
    }


def route_node_summaries(graph: dict[str, Any], route: list[str]) -> list[dict[str, Any]]:
    nodes = graph.get("nodes", {})
    return [short_node(nodes.get(node_id, {})) for node_id in route]


def next_action_for(active: dict[str, Any], evidence_strength: str, claim_readiness: str) -> str:
    kind = active.get("kind", "")
    status = active.get("status", "")
    if status == "blocked":
        return "Resolve the blocker or ask the user/OpenScience supervisor for a decision."
    if kind == "intake":
        return "Run scouting to identify baselines, metrics, evidence gaps, and the first validation route."
    if kind == "scout":
        return "Generate 2-3 testable ideas and select the cheapest useful experiment."
    if kind == "idea":
        return "Write an experiment contract, run a smoke check if authorized, and package evidence."
    if kind == "experiment":
        if evidence_strength in {"has-evidence", "reviewed"}:
            return "Run ds-lite-review before promoting any claim into analysis."
        return "Package and validate the claim-bearing evidence; ordinary artifacts and logs do not satisfy the gate."
    if kind == "review":
        if evidence_strength != "reviewed":
            return "Complete a typed review result before promoting any claim into analysis."
        return "Analyze only passing review evidence; otherwise keep the experiment actionable and record follow-up."
    if kind in {"analysis", "write", "finalize"}:
        return "Decide whether to stop, branch the next candidate, or hand off the reviewed claim."
    if kind == "decision":
        if claim_readiness == "blocked":
            return "Resolve the typed evidence or review blocker before selecting another claim-bearing action."
        return "Execute exactly one bounded next action: exploit, branch, debug, review, analysis, stop, or ask-human."
    return "Inspect STATUS.md, RESEARCH_MAP.md, and linked artifacts before choosing the next action."


def default_work_unit(graph: dict[str, Any], route: list[str]) -> dict[str, Any]:
    nodes = graph.get("nodes", {})
    has_experiment = any(nodes.get(node_id, {}).get("kind") == "experiment" for node_id in route)
    evidence_refs: list[str] = []
    for node_id in route:
        for value in evidence_manifest_paths(nodes.get(node_id, {})):
            append_unique(evidence_refs, value)
    return {
        "schema_version": ds_lite_protocol.WORK_UNIT_SCHEMA,
        "work_unit_id": "legacy-active-route",
        "title": "Legacy active route",
        "goal": "Continue the current Graph route without changing Graph v2.",
        "execution_mode": "none",
        "profile_id": "experiment-run" if has_experiment else "core-planning",
        "state": "active",
        "prerequisites": [],
        "required_capabilities": ["read"],
        "evidence_requirements": (
            [{"kind": "experiment-pack", "validator": EVIDENCE_SCHEMA}] if has_experiment else []
        ),
        "evidence_refs": evidence_refs,
        "resource_limits": [{"dimension": "actions", "unit": "count", "value": 1}],
        "subjects": [
            {
                "kind": "artifact",
                "id": "graph-state",
                "query_ref": "research/state/graph.json",
            }
        ],
        "active_iteration_ref": "",
        "extensions": {"compatibility": "legacy-graph-derived"},
    }


def load_work_unit(
    root: Path,
    graph: dict[str, Any],
    route: list[str],
) -> tuple[dict[str, Any], list[str], list[str]]:
    path = root / WORK_UNIT_RELATIVE
    if not path.exists():
        return (
            default_work_unit(graph, route),
            [],
            [f"{WORK_UNIT_RELATIVE} is absent; mission used a legacy Graph-derived work unit"],
        )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return ds_lite_protocol.validate_work_unit(payload), [], []
    except (OSError, UnicodeError, json.JSONDecodeError, ds_lite_protocol.ProtocolError) as exc:
        return default_work_unit(graph, route), [f"work unit is invalid: {exc}"], []


def route_evidence_nodes(graph: dict[str, Any], route: list[str]) -> dict[str, str]:
    linked: dict[str, str] = {}
    for node_id in route:
        node = graph.get("nodes", {}).get(node_id, {})
        if node.get("kind") != "experiment":
            continue
        for value in evidence_manifest_paths(node):
            linked[value] = node_id
    return linked


def validate_work_unit_evidence(
    root: Path,
    graph: dict[str, Any],
    route: list[str],
    work_unit: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[str]]:
    requirements = work_unit.get("evidence_requirements", [])
    if not requirements:
        return [], []
    blocking: list[str] = []
    profile_id = str(work_unit.get("profile_id", ""))
    validators = {str(item.get("validator", "")) for item in requirements if isinstance(item, dict)}
    if profile_id in RESERVED_PROFILES:
        return [], [f"profile {profile_id} is reserved / not-validated and has no typed validator"]
    if profile_id != "experiment-run":
        return [], [f"profile validator missing for profile {profile_id}"]
    unsupported = sorted(validators - {EVIDENCE_SCHEMA})
    if unsupported:
        return [], [f"profile validator missing for: {', '.join(unsupported)}"]

    refs = list(work_unit.get("evidence_refs", []))
    if not refs:
        return [], ["claim-bearing work unit has no evidence refs"]
    linked = route_evidence_nodes(graph, route)
    validated: list[dict[str, Any]] = []
    for ref in refs:
        node_id = linked.get(ref)
        if not node_id:
            blocking.append(f"evidence ref is not linked on the active route: {ref}")
            continue
        resolved, problem, is_external = ds_lite_evidence.resolve_protocol_path(root, ref)
        if problem or resolved is None or is_external:
            blocking.append(f"evidence ref cannot be resolved as a project Evidence Pack: {ref}: {problem or 'external'}")
            continue
        try:
            payload = json.loads(resolved.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            blocking.append(f"evidence ref is damaged: {ref}: {exc}")
            continue
        if not isinstance(payload, dict) or payload.get("schema_version") != EVIDENCE_SCHEMA:
            blocking.append(f"evidence ref has invalid schema: {ref}")
            continue
        run_id = str(payload.get("run_id", ""))
        expected_ref = f"research/evidence/{run_id}/manifest.json"
        if ref != expected_ref:
            blocking.append(f"evidence ref does not match its run id: {ref}")
            continue
        if payload.get("node_id") != node_id:
            blocking.append(f"evidence ref node id does not match active-route node {node_id}: {ref}")
            continue
        verification = payload.get("verification")
        if not isinstance(verification, dict) or verification.get("status") != "pass":
            blocking.append(f"typed validator has not recorded pass for evidence ref: {ref}")
            continue
        try:
            manifest, errors, warnings, _thresholds = ds_lite_evidence.verify_pack(root, run_id)
        except (ds_lite_evidence.EvidenceError, OSError, UnicodeError, json.JSONDecodeError) as exc:
            blocking.append(f"typed validator failed for evidence ref {ref}: {exc}")
            continue
        if errors or warnings:
            details = errors + warnings
            blocking.append(f"typed validator failed for evidence ref {ref}: {'; '.join(details)}")
            continue
        validated.append(
            {
                "ref": ref,
                "node_id": node_id,
                "run_id": run_id,
                "status": manifest.get("status", ""),
            }
        )
    return validated, blocking


def review_result_paths(node: dict[str, Any]) -> list[str]:
    return [
        value
        for value in node.get("artifact_paths", [])
        if isinstance(value, str) and value.endswith(".json")
    ]


def evidence_digest_for_refs(root: Path, refs: list[str]) -> tuple[str, str | None]:
    records: list[dict[str, str]] = []
    for ref in refs:
        resolved, problem, is_external = ds_lite_evidence.resolve_protocol_path(root, ref)
        if problem or resolved is None or is_external or not resolved.is_file():
            return "", f"reviewed evidence ref cannot be hashed: {ref}: {problem or 'unavailable'}"
        digest, _size = ds_lite_evidence.hash_file(resolved)
        records.append({"path": ref, "sha256": digest})
    return ds_lite_protocol.evidence_refs_digest(records), None


def validate_route_reviews(
    root: Path,
    graph: dict[str, Any],
    route: list[str],
    work_unit: dict[str, Any],
    validated_evidence: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    nodes = graph.get("nodes", {})
    valid_evidence_refs = {item["ref"] for item in validated_evidence}
    required_validators = {
        str(item.get("validator", ""))
        for item in work_unit.get("evidence_requirements", [])
        if isinstance(item, dict)
    }
    valid_results: list[dict[str, Any]] = []
    blocking: list[str] = []
    compatibility: list[str] = []
    for node_id in route:
        node = nodes.get(node_id, {})
        if node.get("kind") != "review":
            continue
        paths = review_result_paths(node)
        if not paths:
            compatibility.append(f"review node {node_id} has no {ds_lite_protocol.REVIEW_RESULT_SCHEMA} sidecar")
            continue
        for ref in paths:
            resolved, problem, is_external = ds_lite_evidence.resolve_protocol_path(root, ref)
            if problem or resolved is None or is_external:
                blocking.append(f"review result cannot be resolved: {ref}: {problem or 'external'}")
                continue
            try:
                payload = json.loads(resolved.read_text(encoding="utf-8"))
                result = ds_lite_protocol.validate_review_result(payload)
            except (OSError, UnicodeError, json.JSONDecodeError, ds_lite_protocol.ProtocolError) as exc:
                blocking.append(f"review result is invalid: {ref}: {exc}")
                continue
            if node.get("status") != "done":
                blocking.append(f"review node {node_id} must be done before its typed result is accepted")
                continue
            if result["review_node_id"] != node_id:
                blocking.append(f"review result node id does not match {node_id}: {ref}")
                continue
            if result["work_unit_id"] != work_unit.get("work_unit_id"):
                blocking.append(f"review result work unit does not match active work unit: {ref}")
                continue
            if result["profile_id"] != work_unit.get("profile_id"):
                blocking.append(f"review result profile does not match active work unit: {ref}")
                continue
            if result["evidence_validator"] not in required_validators:
                blocking.append(f"review result validator does not match active work unit: {ref}")
                continue
            reviewed_id = result["reviewed_node_id"]
            reviewed_node = nodes.get(reviewed_id, {})
            if reviewed_id not in route or reviewed_node.get("kind") != "experiment":
                blocking.append(f"reviewed node is not an experiment on the active route: {ref}")
                continue
            if not any(
                edge.get("to") == node_id and edge.get("relation") in PROGRESSION_RELATIONS
                for edge in graph.get("adjacency", {}).get(reviewed_id, [])
            ):
                blocking.append(f"review node is not a direct progression child of {reviewed_id}: {ref}")
                continue
            reviewed_refs = set(result["reviewed_evidence_refs"])
            if not reviewed_refs or not reviewed_refs.issubset(valid_evidence_refs):
                blocking.append(f"review result references evidence that did not pass its typed validator: {ref}")
                continue
            if not reviewed_refs.issubset(set(reviewed_node.get("evidence_paths", []))):
                blocking.append(f"reviewed evidence refs are not linked to node {reviewed_id}: {ref}")
                continue
            if not reviewed_refs.issubset(set(node.get("evidence_paths", []))):
                blocking.append(f"reviewed evidence refs are not linked to review node {node_id}: {ref}")
                continue
            digest, digest_problem = evidence_digest_for_refs(root, result["reviewed_evidence_refs"])
            if digest_problem or digest != result["evidence_digest"]:
                blocking.append(digest_problem or f"review result evidence digest mismatch: {ref}")
                continue
            if result["review_artifact_ref"] not in node.get("artifact_paths", []):
                blocking.append(f"review artifact ref is not linked to review node {node_id}: {ref}")
                continue
            valid_results.append({"ref": ref, **result})
    return valid_results, blocking, compatibility


def derive_evidence_state(
    root: Path,
    graph: dict[str, Any],
    route: list[str],
) -> dict[str, Any]:
    work_unit, work_unit_errors, compatibility = load_work_unit(root, graph, route)
    validated, evidence_blocking = validate_work_unit_evidence(root, graph, route, work_unit)
    reviews, review_blocking, review_compatibility = validate_route_reviews(
        root, graph, route, work_unit, validated
    )
    compatibility.extend(review_compatibility)
    blocking = evidence_blocking + review_blocking
    requirements = work_unit.get("evidence_requirements", [])
    if reviews:
        strength = "reviewed"
    elif validated:
        strength = "has-evidence"
    elif requirements:
        strength = "needs-evidence"
    else:
        strength = "planning"

    if not requirements:
        readiness = "none"
    elif work_unit_errors or blocking or not validated:
        readiness = "blocked"
    elif reviews:
        latest = reviews[-1]
        readiness = latest["claim_assessment"] if latest["verdict"] == "pass" else "blocked"
        if readiness == "none":
            readiness = "inconclusive"
    else:
        readiness = "inconclusive"

    negative = [item for item in validated if item.get("status") == "failed"]
    detail = {
        "work_unit_id": work_unit.get("work_unit_id", ""),
        "profile_id": work_unit.get("profile_id", ""),
        "claim_requirement_count": len(requirements),
        "validated_evidence_count": len(validated),
        "validated_evidence_refs": [item["ref"] for item in validated],
        "negative_evidence_count": len(negative),
        "negative_evidence_refs": [item["ref"] for item in negative],
        "review_result_count": len(reviews),
        "latest_evidence_ref": validated[-1]["ref"] if validated else "",
        "latest_review_ref": reviews[-1]["ref"] if reviews else "",
        "blocking_reasons": work_unit_errors + blocking,
    }
    return {
        "work_unit": work_unit,
        "evidence_strength": strength,
        "claim_readiness": readiness,
        "evidence_detail": detail,
        "review_results": reviews,
        "errors": work_unit_errors + review_blocking,
        "warnings": evidence_blocking,
        "compatibility_warnings": compatibility,
    }


def read_json_object(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def metric_surface_label(metric_name: str) -> str:
    lowered = metric_name.lower()
    if "auc" in lowered or "aggregate" in lowered:
        return "aggregate"
    if "final" in lowered:
        return "final"
    if "early" in lowered or "smoke" in lowered:
        return "early"
    return "primary"


def inferred_metric_surfaces(node: dict[str, Any]) -> list[dict[str, Any]]:
    text = f"{node.get('title', '')} {node.get('summary', '')}".lower()
    inferred: list[dict[str, Any]] = []
    for token, surface in (("auc", "aggregate"), ("final", "final"), ("early", "early")):
        if token in text:
            inferred.append(
                {
                    "node_id": node.get("id", ""),
                    "run_id": "",
                    "name": token,
                    "direction": "observe",
                    "threshold": None,
                    "surface": surface,
                    "budget": {},
                    "verification_status": "",
                    "source": "node-summary",
                }
            )
    return inferred


def metric_surfaces_for_node(root: Path, node: dict[str, Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for manifest_value in evidence_manifest_paths(node):
        manifest_path, problem = resolve_graph_path(root, manifest_value)
        if problem:
            continue
        manifest = read_json_object(manifest_path)
        if not manifest:
            continue
        contract_value = str(manifest.get("contract_path") or "")
        if not contract_value:
            contract_value = (PurePosixPath(manifest_value).parent / "contract.json").as_posix()
        contract_path, contract_problem = resolve_graph_path(root, contract_value)
        if contract_problem:
            continue
        contract = read_json_object(contract_path)
        if not contract:
            continue
        budget = contract.get("budget") if isinstance(contract.get("budget"), dict) else {}
        verification = manifest.get("verification") if isinstance(manifest.get("verification"), dict) else {}
        threshold_records = verification.get("thresholds") if isinstance(verification.get("thresholds"), list) else []
        thresholds_by_name = {
            str(item.get("name")): item
            for item in threshold_records
            if isinstance(item, dict) and str(item.get("name", "")).strip()
        }
        for metric in contract.get("metrics", []):
            if not isinstance(metric, dict):
                continue
            name = str(metric.get("name", "")).strip()
            direction = str(metric.get("direction", "")).strip()
            if not name or not direction:
                continue
            threshold_record = thresholds_by_name.get(name, {})
            records.append(
                {
                    "node_id": node.get("id", ""),
                    "run_id": manifest.get("run_id", ""),
                    "name": name,
                    "direction": direction,
                    "threshold": metric.get("threshold", threshold_record.get("threshold")),
                    "surface": metric_surface_label(name),
                    "budget": budget,
                    "verification_status": verification.get("status", ""),
                    "source": contract_value,
                }
            )
    return records or inferred_metric_surfaces(node)


def metric_surfaces_for_route(root: Path, graph: dict[str, Any], route: list[str]) -> list[dict[str, Any]]:
    surfaces: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for node_id in route:
        node = graph.get("nodes", {}).get(node_id, {})
        if node.get("kind") not in {"experiment", "review", "analysis", "write", "finalize"}:
            continue
        for record in metric_surfaces_for_node(root, node):
            key = (str(record.get("run_id") or record.get("node_id", "")), str(record.get("name", "")))
            if key in seen:
                continue
            seen.add(key)
            surfaces.append(record)
    return surfaces


def build_mission(root: Path, graph: dict[str, Any]) -> dict[str, Any]:
    nodes = graph.get("nodes", {})
    adjacency = graph.get("adjacency", {})
    active_id = graph.get("active_node_id", "")
    root_id = graph.get("root_node_id", "")
    active = nodes.get(active_id, {})
    route = find_route(graph, root_id, active_id, mode="progression") if active_id else []
    route_set = set(route)

    warning_nodes: list[str | None] = []
    errors, all_warnings = validate_graph(root, graph, check_paths=True, warning_nodes=warning_nodes)
    if map_is_stale(root, graph):
        all_warnings.append("RESEARCH_MAP.md is missing or stale; run render-map")
        warning_nodes.append(None)
    route_warnings: list[str] = []
    off_route_warnings: list[str] = []
    for message, node_id in zip(all_warnings, warning_nodes):
        if node_id is not None and node_id not in route_set:
            off_route_warnings.append(message)
        else:
            route_warnings.append(message)

    evidence_state = derive_evidence_state(root, graph, route)
    errors.extend(evidence_state["errors"])
    route_warnings.extend(evidence_state["warnings"])

    candidate_queue: list[dict[str, Any]] = []
    rollback_targets: list[dict[str, str]] = []
    supersedes: list[dict[str, str]] = []
    blockers: list[dict[str, str]] = []
    for source, edges in adjacency.items():
        for edge in edges:
            target = str(edge.get("to", ""))
            relation = edge.get("relation", "")
            if relation == "branch" and target not in route_set and target in nodes:
                candidate_queue.append(short_node(nodes[target]))
            elif relation == "rollback":
                rollback_targets.append(
                    {"from": str(source), "to": target, "reason": str(edge.get("reason", ""))}
                )
            elif relation == "supersedes":
                supersedes.append({"from": str(source), "to": target, "reason": str(edge.get("reason", ""))})
            elif relation == "blocks":
                blockers.append({"from": str(source), "to": target, "reason": str(edge.get("reason", ""))})

    blocked_nodes = [short_node(node) for node in nodes.values() if node.get("status") == "blocked"]
    active_route_blocked = [
        short_node(nodes[node_id])
        for node_id in route
        if nodes.get(node_id, {}).get("status") == "blocked"
    ]
    off_route_blocked = [
        short_node(node)
        for node_id, node in nodes.items()
        if node.get("status") == "blocked" and node_id not in route_set
    ]
    active_route_blocker_edges = [item for item in blockers if item.get("from") in route_set]
    review_needs_human = any(
        item.get("verdict") == "needs-human" for item in evidence_state["review_results"]
    )
    work_unit_blocked = evidence_state["work_unit"].get("state") == "blocked"
    waiting_for_user = bool(
        active_route_blocked or active_route_blocker_edges or review_needs_human or work_unit_blocked
    )
    experiment_queue = [
        short_node(node)
        for node in nodes.values()
        if node.get("kind") == "experiment" and node.get("status") in {"active", "proposed", "blocked"}
    ]
    latest_result = {}
    for node_id in reversed(route):
        node = nodes.get(node_id, {})
        if node.get("kind") in {"experiment", "review", "analysis", "write", "finalize"}:
            latest_result = short_node(node)
            break

    validation_ok = not errors and not route_warnings
    mission = {
        "ok": True,
        "schema_version": graph.get("schema_version"),
        "revision": graph.get("revision", 0),
        "project": graph.get("project", {}),
        "root_node_id": root_id,
        "active_node_id": active_id,
        "stage": active.get("kind", ""),
        "active": short_node(active),
        "active_route": route,
        "active_route_nodes": route_node_summaries(graph, route),
        "latest_result": latest_result,
        "next_action": next_action_for(
            active,
            evidence_state["evidence_strength"],
            evidence_state["claim_readiness"],
        ),
        "candidate_queue": candidate_queue,
        "experiment_queue": experiment_queue,
        "blocked_nodes": blocked_nodes,
        "blockers": blockers,
        "rollback_targets": rollback_targets,
        "supersedes": supersedes,
        "metric_surfaces": metric_surfaces_for_route(root, graph, route),
        "work_unit": evidence_state["work_unit"],
        "evidence_strength": evidence_state["evidence_strength"],
        "claim_readiness": evidence_state["claim_readiness"],
        "evidence_detail": evidence_state["evidence_detail"],
        "waiting_for_user": waiting_for_user,
        "waiting_detail": {
            "active_route_blocked_count": len(active_route_blocked),
            "off_route_blocked_count": len(off_route_blocked),
            "active_route_blocker_edge_count": len(active_route_blocker_edges),
            "review_needs_human": review_needs_human,
            "work_unit_blocked": work_unit_blocked,
        },
        "readiness_rules": READINESS_RULES,
        "validation": {
            "ok": validation_ok,
            "errors": errors,
            "warnings": route_warnings,
            "off_route_warnings": off_route_warnings,
            "compatibility_warnings": evidence_state["compatibility_warnings"],
            "map_stale": map_is_stale(root, graph),
        },
    }
    return mission


def render_mission_markdown(mission: dict[str, Any]) -> str:
    project = mission.get("project", {})
    active = mission.get("active", {})
    latest = mission.get("latest_result") or {}
    work_unit = mission.get("work_unit") or {}
    evidence_detail = mission.get("evidence_detail") or {}
    waiting_detail = mission.get("waiting_detail") or {}
    lines = [
        "# Status",
        "",
        "## Mission Board",
        "",
        f"- Project: {project.get('title') or project.get('id') or 'Untitled Project'}",
        f"- Active node: `{mission.get('active_node_id', '')}`",
        f"- Stage: {mission.get('stage', '') or 'unknown'}",
        f"- Status: {active.get('status', '') or 'unknown'}",
        f"- Work unit: `{work_unit.get('work_unit_id', '')}`",
        f"- Profile: `{work_unit.get('profile_id', '')}`",
        f"- Execution mode: {work_unit.get('execution_mode', '') or 'unknown'}",
        f"- Evidence strength: {mission.get('evidence_strength', '')}",
        f"- Claim readiness: {mission.get('claim_readiness', '')}",
        f"- Validated evidence: {evidence_detail.get('validated_evidence_count', 0)}",
        f"- Negative evidence: {evidence_detail.get('negative_evidence_count', 0)}",
        f"- Typed review results: {evidence_detail.get('review_result_count', 0)}",
        f"- Latest evidence ref: {evidence_detail.get('latest_evidence_ref') or 'none'}",
        f"- Latest review ref: {evidence_detail.get('latest_review_ref') or 'none'}",
        f"- Waiting for user: {'yes' if mission.get('waiting_for_user') else 'no'}",
        f"- Active-route blocked: {waiting_detail.get('active_route_blocked_count', 0)}",
        f"- Off-route blocked: {waiting_detail.get('off_route_blocked_count', 0)}",
        "",
        "## Current Summary",
        "",
        str(active.get("summary") or "No active summary recorded."),
        "",
        "## Latest Result",
        "",
    ]
    if latest:
        lines.extend(
            [
                f"- `{latest.get('id')}` - {latest.get('kind')}: {latest.get('title')} [{latest.get('status')}]",
                f"- Summary: {latest.get('summary')}",
            ]
        )
    else:
        lines.append("- No experiment, review, or analysis result on the active route yet.")

    lines.extend(["", "## Metric Surface", ""])
    metric_surfaces = mission.get("metric_surfaces", [])
    if metric_surfaces:
        for item in metric_surfaces:
            budget = item.get("budget") if isinstance(item.get("budget"), dict) else {}
            budget_text = ""
            if budget:
                budget_text = f", budget={budget.get('value')} {budget.get('unit')}"
            threshold = item.get("threshold")
            threshold_text = "" if threshold is None else f", threshold={threshold}"
            lines.append(
                f"- `{item.get('name')}`: surface={item.get('surface')}, direction={item.get('direction')}"
                f"{threshold_text}{budget_text}"
            )
    else:
        lines.append("- No metric contract on the active route yet.")
    lines.extend(
        [
            "",
            "## Next Action",
            "",
            str(mission.get("next_action") or "Inspect the active node and choose the next bounded action."),
            "",
            "## Active Route",
            "",
        ]
    )
    for node in mission.get("active_route_nodes", []):
        lines.append(f"- `{node.get('id')}` - {node.get('kind')}: {node.get('title')} [{node.get('status')}]")
    if not mission.get("active_route_nodes"):
        lines.append("- No progression route found.")

    lines.extend(["", "## Experiment Queue", ""])
    experiments = mission.get("experiment_queue", [])
    if experiments:
        for node in experiments:
            lines.append(f"- `{node.get('id')}` - {node.get('title')} [{node.get('status')}]")
    else:
        lines.append("- No active or proposed experiment nodes.")

    lines.extend(["", "## Candidate Queue", ""])
    candidates = mission.get("candidate_queue", [])
    if candidates:
        for node in candidates:
            lines.append(f"- `{node.get('id')}` - {node.get('title')} [{node.get('status')}]")
    else:
        lines.append("- No off-route branch candidates.")

    lines.extend(["", "## Blockers", ""])
    blocked = mission.get("blocked_nodes", [])
    blockers = mission.get("blockers", [])
    if blocked or blockers:
        for node in blocked:
            lines.append(f"- `{node.get('id')}` - {node.get('title')} [{node.get('status')}]")
        for item in blockers:
            lines.append(f"- `{item.get('from')}` blocks `{item.get('to')}`: {item.get('reason')}")
    else:
        lines.append("- None.")

    lines.extend(["", "## Rollback Targets", ""])
    rollbacks = mission.get("rollback_targets", [])
    if rollbacks:
        for item in rollbacks:
            lines.append(f"- `{item.get('from')}` -> `{item.get('to')}`: {item.get('reason')}")
    else:
        lines.append("- None recorded.")

    lines.extend(["", "## Validation", ""])
    validation = mission.get("validation", {})
    lines.append(f"- Active route valid: {'yes' if validation.get('ok') else 'no'}")
    lines.append(f"- Map stale: {'yes' if validation.get('map_stale') else 'no'}")
    errors = validation.get("errors") or []
    if errors:
        lines.append("- Errors:")
        for error in errors:
            lines.append(f"  - {error}")
    warnings = validation.get("warnings") or []
    if warnings:
        lines.append("- Warnings:")
        for warning in warnings:
            lines.append(f"  - {warning}")
    off_route_warnings = validation.get("off_route_warnings") or []
    if off_route_warnings:
        lines.append("- Off-route warnings preserved:")
        for warning in off_route_warnings:
            lines.append(f"  - {warning}")
    evidence_blockers = evidence_detail.get("blocking_reasons") or []
    if evidence_blockers:
        lines.append("- Evidence blockers:")
        for blocker in evidence_blockers:
            lines.append(f"  - {blocker}")
    compatibility_warnings = validation.get("compatibility_warnings") or []
    if compatibility_warnings:
        lines.append("- Compatibility warnings:")
        for warning in compatibility_warnings:
            lines.append(f"  - {warning}")

    lines.extend(["", "## Readiness Rules", ""])
    for rule in mission.get("readiness_rules", []):
        lines.append(f"- {rule}")
    lines.extend(["", "## Last Updated", "", utc_now()])
    return "\n".join(lines).rstrip() + "\n"


def render_status(root: Path, graph: dict[str, Any]) -> Path:
    mission = build_mission(root, graph)
    output = root / "STATUS.md"
    atomic_write_text(output, render_mission_markdown(mission))
    return output


def map_revision(root: Path) -> int | None:
    path = root / "RESEARCH_MAP.md"
    if not path.exists():
        return None
    match = MAP_REVISION_RE.search(path.read_text(encoding="utf-8"))
    return int(match.group(1)) if match else None


def map_is_stale(root: Path, graph: dict[str, Any]) -> bool:
    return map_revision(root) != graph.get("revision", 0)


def new_graph_from_template(project_id: str, title: str, question: str) -> dict[str, Any]:
    now = utc_now()
    root_node = {
        "id": "intake-root",
        "kind": "intake",
        "status": "active",
        "title": "Project intake",
        "summary": question or "Project initialized with DeepScientist Lite.",
        "artifact_paths": [],
        "memory_paths": [],
        "evidence_paths": ["PROJECT.md", "STATUS.md"],
        "created_at": now,
        "updated_at": now,
    }
    content = render_template(
        "research/state/graph.json",
        {
            "schema_version": SCHEMA_VERSION,
            "project_id_json": json.dumps(project_id, ensure_ascii=False),
            "project_title_json": json.dumps(title, ensure_ascii=False),
            "root_node_json": json.dumps(root_node, ensure_ascii=False, indent=4),
        },
    )
    graph = json.loads(content)
    errors, _warnings = validate_graph(Path.cwd(), graph, check_paths=False)
    if errors:
        raise CliError("Graph template produced invalid state.", details=errors)
    return graph


def cmd_init(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    ensure_dirs(root)
    title = value_or_file(args.title, args.title_file, "title") or root.name
    question = value_or_file(args.question, args.question_file, "question")
    project_id = args.project_id or slugify(title, fallback="ds-lite-project")
    with graph_lock(root):
        if state_path(root).exists():
            graph = load_graph(root)
            graph, backup = prepare_graph_for_write(root, graph, parse_external_maps(args.external_map))
            save_graph(root, graph)
            if args.render:
                render_map(root, graph)
            emit(
                {
                    "ok": True,
                    "status": "exists",
                    "graph": str(state_path(root)),
                    "schema_version": graph.get("schema_version"),
                    "revision": graph.get("revision", 0),
                    "backup": str(backup) if backup else "",
                }
            )
            return 0

        today = datetime.now().strftime("%Y-%m-%d")
        values = {
            "project_title": title,
            "question": question or "TBD.",
            "question_json": json.dumps(question or "Define the first bounded research goal.", ensure_ascii=False),
            "date": today,
        }
        created = []
        for relative, template_name in (
            ("PROJECT.md", "PROJECT.md"),
            ("STATUS.md", "STATUS.md"),
            ("run_research.sh", "run_research.sh"),
            ("run_experiment.sh", "run_experiment.sh"),
            ("run_review.sh", "run_review.sh"),
            ("run_analysis.sh", "run_analysis.sh"),
            ("tools/ds_lite_runtime.sh", "tools/ds_lite_runtime.sh"),
            (WORK_UNIT_RELATIVE, "research/work-unit.json"),
        ):
            if write_if_missing(root / relative, render_template(template_name, values)):
                created.append(relative)
        graph = new_graph_from_template(project_id, title, question)
        save_graph(root, graph)
        if args.render:
            render_map(root, graph)
            created.append("RESEARCH_MAP.md")
        emit(
            {
                "ok": True,
                "status": "created",
                "graph": str(state_path(root)),
                "schema_version": SCHEMA_VERSION,
                "revision": 0,
                "active_node_id": "intake-root",
                "created": created,
            }
        )
    return 0


def cmd_add_node(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    title = value_or_file(args.title, args.title_file, "title", required=True)
    summary = value_or_file(args.summary, args.summary_file, "summary")
    reason = value_or_file(args.reason, args.reason_file, "reason")

    def mutate(graph: dict[str, Any]) -> dict[str, Any]:
        node_id = args.id or make_node_id(graph, args.kind, title)
        if node_id in graph.get("nodes", {}):
            raise CliError(f"Node already exists: {node_id}")
        now = utc_now()
        node = {
            "id": node_id,
            "kind": args.kind,
            "status": args.status,
            "title": title,
            "summary": summary,
            "artifact_paths": [normalize_graph_path(root, item) for item in args.artifact_path],
            "memory_paths": [normalize_graph_path(root, item) for item in args.memory_path],
            "evidence_paths": [normalize_graph_path(root, item) for item in args.evidence_path],
            "created_at": now,
            "updated_at": now,
        }
        graph.setdefault("nodes", {})[node_id] = node
        graph.setdefault("adjacency", {}).setdefault(node_id, [])
        if args.parent:
            add_edge_obj(
                graph,
                args.parent,
                node_id,
                args.relation,
                reason or f"{args.relation} to {node_id}",
                normalize_graph_path(root, args.edge_artifact_path) if args.edge_artifact_path else "",
            )
        elif graph.get("root_node_id"):
            raise CliError("Non-root nodes require --parent so they remain reachable through progression edges.")
        else:
            graph["root_node_id"] = node_id
        if args.active:
            set_active_in_graph(graph, node_id, now)
        return {"node_id": node_id}

    graph, payload, backup = mutation_transaction(root, args, mutate)
    emit(
        {
            "ok": True,
            **payload,
            "active_node_id": graph.get("active_node_id", ""),
            "revision": graph["revision"],
            "backup": str(backup) if backup else "",
        }
    )
    return 0


def cmd_update_node(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    title = value_or_file(args.title, args.title_file, "title")
    summary = value_or_file(args.summary, args.summary_file, "summary")
    if not any((title, summary, args.kind)):
        raise CliError("update-node requires --title/--title-file, --summary/--summary-file, or --kind.")

    def mutate(graph: dict[str, Any]) -> dict[str, Any]:
        node = require_node(graph, args.node)
        if title:
            node["title"] = title
        if summary:
            node["summary"] = summary
        if args.kind:
            node["kind"] = args.kind
        node["updated_at"] = monotonic_node_timestamp(node)
        return {"node_id": args.node}

    graph, payload, backup = mutation_transaction(root, args, mutate)
    emit({"ok": True, **payload, "revision": graph["revision"], "backup": str(backup) if backup else ""})
    return 0


def cmd_add_edge(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    reason = value_or_file(args.reason, args.reason_file, "reason")

    def mutate(graph: dict[str, Any]) -> dict[str, Any]:
        added = add_edge_obj(
            graph,
            args.source,
            args.target,
            args.relation,
            reason,
            normalize_graph_path(root, args.artifact_path) if args.artifact_path else "",
        )
        return {"added": added, "from": args.source, "to": args.target, "relation": args.relation}

    graph, payload, backup = mutation_transaction(root, args, mutate)
    emit({"ok": True, **payload, "revision": graph["revision"], "backup": str(backup) if backup else ""})
    return 0


def cmd_link_path(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    field = f"{args.type}_paths"

    def mutate(graph: dict[str, Any]) -> dict[str, Any]:
        node = require_node(graph, args.node)
        path = normalize_graph_path(root, args.path)
        append_unique(node.setdefault(field, []), path)
        node["updated_at"] = monotonic_node_timestamp(node)
        return {"node_id": args.node, "path_type": args.type, "path": path}

    graph, payload, backup = mutation_transaction(root, args, mutate)
    emit({"ok": True, **payload, "revision": graph["revision"], "backup": str(backup) if backup else ""})
    return 0


def cmd_link_artifact(args: argparse.Namespace) -> int:
    print("DEPRECATED: use link-path --type artifact.", file=sys.stderr)
    args.type = "artifact"
    return cmd_link_path(args)


def set_active_in_graph(graph: dict[str, Any], target_id: str, now: str | None = None) -> None:
    target = require_node(graph, target_id)
    timestamp = now or utc_now()
    for node in graph.get("nodes", {}).values():
        if node.get("status") == "active" and node.get("id") != target_id:
            node["status"] = "done"
            node["updated_at"] = monotonic_node_timestamp(node, timestamp)
    target["status"] = "active"
    target["updated_at"] = monotonic_node_timestamp(target, timestamp)
    graph["active_node_id"] = target_id


def cmd_set_active(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()

    def mutate(graph: dict[str, Any]) -> dict[str, Any]:
        set_active_in_graph(graph, args.node)
        return {"active_node_id": args.node}

    graph, payload, backup = mutation_transaction(root, args, mutate)
    emit({"ok": True, **payload, "revision": graph["revision"], "backup": str(backup) if backup else ""})
    return 0


def cmd_set_status(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()

    def mutate(graph: dict[str, Any]) -> dict[str, Any]:
        node = require_node(graph, args.node)
        if args.status == "active":
            set_active_in_graph(graph, args.node)
        else:
            node["status"] = args.status
            node["updated_at"] = monotonic_node_timestamp(node)
            if graph.get("active_node_id") == args.node:
                graph["active_node_id"] = ""
        return {"node_id": args.node, "status": args.status}

    graph, payload, backup = mutation_transaction(root, args, mutate)
    emit({"ok": True, **payload, "revision": graph["revision"], "backup": str(backup) if backup else ""})
    return 0


def cmd_trace(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    graph = load_graph(root)
    target = args.node or graph.get("active_node_id", "")
    require_node(graph, target)
    route = find_route(graph, graph.get("root_node_id", ""), target, mode=args.mode)
    payload = {
        "ok": bool(route),
        "schema_version": graph.get("schema_version"),
        "revision": graph.get("revision", 0),
        "mode": args.mode,
        "target": target,
        "route": [
            {
                "id": node_id,
                "kind": graph["nodes"][node_id].get("kind", ""),
                "status": graph["nodes"][node_id].get("status", ""),
                "title": graph["nodes"][node_id].get("title", ""),
            }
            for node_id in route
        ],
    }
    if args.format == "markdown":
        print(f"# DS Lite Trace: {target}")
        print("")
        if route:
            for index, node_id in enumerate(route, start=1):
                node = graph["nodes"][node_id]
                print(f"{index}. `{node_id}` - {node.get('kind', '')}: {node.get('title', '')} [{node.get('status', '')}]")
        else:
            print(f"No {args.mode} route found from root to target node.")
    else:
        emit(payload)
    return 0 if route else 2


def cmd_trace_artifact(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    graph = load_graph(root)
    query = normalize_graph_path(root, args.path)
    matches = []
    for node_id, node in graph.get("nodes", {}).items():
        combined = node.get("artifact_paths", []) + node.get("memory_paths", []) + node.get("evidence_paths", [])
        if query in combined:
            matches.append(
                {
                    "id": node_id,
                    "kind": node.get("kind", ""),
                    "status": node.get("status", ""),
                    "title": node.get("title", ""),
                }
            )
    emit(
        {
            "ok": True,
            "schema_version": graph.get("schema_version"),
            "revision": graph.get("revision", 0),
            "path": query,
            "count": len(matches),
            "nodes": matches,
        }
    )
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    graph = load_graph(root)
    warning_nodes: list[str | None] = []
    errors, all_warnings = validate_graph(root, graph, check_paths=True, warning_nodes=warning_nodes)
    if map_is_stale(root, graph):
        all_warnings.append("RESEARCH_MAP.md is missing or stale; run render-map")
        warning_nodes.append(None)

    active_id = graph.get("active_node_id", "")
    active_route = find_route(graph, graph.get("root_node_id", ""), active_id, mode="progression") if active_id else []
    route_nodes = set(active_route)
    warnings: list[str] = []
    off_route_warnings: list[str] = []
    for message, node_id in zip(all_warnings, warning_nodes):
        if args.scope == "active-route" and node_id is not None and node_id not in route_nodes:
            off_route_warnings.append(message)
        else:
            warnings.append(message)

    ok = not errors and (not args.strict or not warnings)
    emit(
        {
            "ok": ok,
            "strict": args.strict,
            "scope": args.scope,
            "schema_version": graph.get("schema_version"),
            "revision": graph.get("revision", 0),
            "active_node_id": active_id,
            "active_route": active_route,
            "errors": errors,
            "warnings": warnings,
            "off_route_warnings": off_route_warnings,
            "warning_count": len(all_warnings),
            "graph": str(state_path(root)),
        }
    )
    return 0 if ok else 1


def cmd_render_map(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    with graph_lock(root):
        graph = load_graph(root)
        graph, backup = prepare_graph_for_write(root, graph, parse_external_maps(args.external_map))
        save_graph(root, graph)
        output = render_map(root, graph)
    emit(
        {
            "ok": True,
            "path": str(output),
            "schema_version": graph.get("schema_version"),
            "revision": graph.get("revision", 0),
            "backup": str(backup) if backup else "",
        }
    )
    return 0


def cmd_mission(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    graph = load_graph(root)
    mission = build_mission(root, graph)
    if args.format == "markdown":
        print(render_mission_markdown(mission), end="")
    else:
        emit(mission)
    return 0


def cmd_render_status(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    graph = load_graph(root)
    output = render_status(root, graph)
    emit(
        {
            "ok": True,
            "path": str(output),
            "schema_version": graph.get("schema_version"),
            "revision": graph.get("revision", 0),
            "active_node_id": graph.get("active_node_id", ""),
        }
    )
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    graph = load_graph(root)
    active_id = graph.get("active_node_id", "")
    active = graph.get("nodes", {}).get(active_id, {})
    warnings = []
    if graph.get("schema_version") == SCHEMA_V1:
        warnings.append("graph v1 is readable but must be migrated before the next state change")
    stale = map_is_stale(root, graph)
    if stale:
        warnings.append("RESEARCH_MAP.md is missing or stale")
    emit(
        {
            "ok": True,
            "schema_version": graph.get("schema_version"),
            "revision": graph.get("revision", 0),
            "project": graph.get("project", {}),
            "root_node_id": graph.get("root_node_id", ""),
            "active_node_id": active_id,
            "active": active,
            "node_count": len(graph.get("nodes", {})),
            "edge_count": sum(len(edges) for edges in graph.get("adjacency", {}).values() if isinstance(edges, list)),
            "map_stale": stale,
            "warnings": warnings,
        }
    )
    return 0


def cmd_migrate(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    mappings = parse_external_maps(args.external_map)
    if args.dry_run:
        graph = load_graph(root)
        migrated = migration_preview(root, graph, mappings)
        emit(
            {
                "ok": True,
                "dry_run": True,
                "from": graph.get("schema_version"),
                "to": migrated.get("schema_version"),
                "revision": migrated.get("revision", 0),
                "changed": graph != migrated,
            }
        )
        return 0
    with graph_lock(root):
        graph = load_graph(root)
        if graph.get("schema_version") == SCHEMA_VERSION:
            emit({"ok": True, "status": "already-current", "schema_version": SCHEMA_VERSION, "revision": graph.get("revision", 0)})
            return 0
        migrated, backup = prepare_graph_for_write(root, graph, mappings)
        errors, warnings = validate_graph(root, migrated, check_paths=False)
        if errors:
            raise CliError("Migrated graph is invalid.", details=errors)
        save_graph(root, migrated)
        if args.render:
            render_map(root, migrated)
    emit(
        {
            "ok": True,
            "status": "migrated",
            "schema_version": SCHEMA_VERSION,
            "revision": migrated.get("revision", 0),
            "backup": str(backup) if backup else "",
            "warnings": warnings,
        }
    )
    return 0


def add_root(subparser: argparse.ArgumentParser) -> None:
    subparser.add_argument("--root", default=".", help="Project root. Defaults to current directory.")


def add_render_options(subparser: argparse.ArgumentParser) -> None:
    subparser.set_defaults(render=True)
    subparser.add_argument("--render", dest="render", action="store_true", help="Render RESEARCH_MAP.md (default).")
    subparser.add_argument("--no-render", dest="render", action="store_false", help="Skip RESEARCH_MAP.md rendering.")


def add_write_options(subparser: argparse.ArgumentParser) -> None:
    add_root(subparser)
    add_render_options(subparser)
    subparser.add_argument("--expected-revision", type=int, default=None, help="Reject the write unless graph revision matches.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage DeepScientist Lite research state graphs.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init = subparsers.add_parser("init", help="Initialize DS Lite files or migrate an existing graph.")
    add_root(init)
    add_render_options(init)
    init.add_argument("--title", default="")
    init.add_argument("--title-file", default="")
    init.add_argument("--project-id", default="")
    init.add_argument("--question", default="")
    init.add_argument("--question-file", default="")
    init.add_argument("--external-map", action="append", default=[])
    init.set_defaults(func=cmd_init)

    add_node = subparsers.add_parser("add-node", help="Add a graph node.")
    add_write_options(add_node)
    add_node.add_argument("--id", default="")
    add_node.add_argument("--kind", required=True, choices=sorted(NODE_KINDS))
    add_node.add_argument("--status", default="proposed", choices=sorted(NODE_STATUSES))
    add_node.add_argument("--title", default="")
    add_node.add_argument("--title-file", default="")
    add_node.add_argument("--summary", default="")
    add_node.add_argument("--summary-file", default="")
    add_node.add_argument("--parent", default="")
    add_node.add_argument("--relation", default="next", choices=sorted(PROGRESSION_RELATIONS))
    add_node.add_argument("--reason", default="")
    add_node.add_argument("--reason-file", default="")
    add_node.add_argument("--edge-artifact-path", default="")
    add_node.add_argument("--artifact-path", action="append", default=[])
    add_node.add_argument("--memory-path", action="append", default=[])
    add_node.add_argument("--evidence-path", action="append", default=[])
    add_node.add_argument("--active", action="store_true")
    add_node.set_defaults(func=cmd_add_node)

    update_node = subparsers.add_parser("update-node", help="Update an existing graph node.")
    add_write_options(update_node)
    update_node.add_argument("--node", required=True)
    update_node.add_argument("--kind", choices=sorted(NODE_KINDS), default="")
    update_node.add_argument("--title", default="")
    update_node.add_argument("--title-file", default="")
    update_node.add_argument("--summary", default="")
    update_node.add_argument("--summary-file", default="")
    update_node.set_defaults(func=cmd_update_node)

    add_edge = subparsers.add_parser("add-edge", help="Add an edge between existing nodes.")
    add_write_options(add_edge)
    add_edge.add_argument("--from", dest="source", required=True)
    add_edge.add_argument("--to", dest="target", required=True)
    add_edge.add_argument("--relation", required=True, choices=sorted(EDGE_RELATIONS))
    add_edge.add_argument("--reason", default="")
    add_edge.add_argument("--reason-file", default="")
    add_edge.add_argument("--artifact-path", default="")
    add_edge.set_defaults(func=cmd_add_edge)

    link_path = subparsers.add_parser("link-path", help="Attach an artifact, memory, or evidence path to a node.")
    add_write_options(link_path)
    link_path.add_argument("--node", required=True)
    link_path.add_argument("--type", required=True, choices=("artifact", "memory", "evidence"))
    link_path.add_argument("--path", required=True)
    link_path.set_defaults(func=cmd_link_path)

    link_artifact = subparsers.add_parser("link-artifact", help="Deprecated alias for link-path --type artifact.")
    add_write_options(link_artifact)
    link_artifact.add_argument("--node", required=True)
    link_artifact.add_argument("--path", required=True)
    link_artifact.set_defaults(func=cmd_link_artifact)

    set_active = subparsers.add_parser("set-active", help="Set the sole active node.")
    add_write_options(set_active)
    set_active.add_argument("--node", required=True)
    set_active.set_defaults(func=cmd_set_active)

    set_status = subparsers.add_parser("set-status", help="Set one node status.")
    add_write_options(set_status)
    set_status.add_argument("--node", required=True)
    set_status.add_argument("--status", required=True, choices=sorted(NODE_STATUSES))
    set_status.set_defaults(func=cmd_set_status)

    trace = subparsers.add_parser("trace", help="Trace a progression or all-edge route from root to a node.")
    add_root(trace)
    trace.add_argument("--node", default="")
    trace.add_argument("--mode", choices=("progression", "all"), default="progression")
    trace.add_argument("--format", choices=("json", "markdown"), default="json")
    trace.set_defaults(func=cmd_trace)

    trace_artifact = subparsers.add_parser("trace-artifact", help="Find nodes linked to a graph path.")
    add_root(trace_artifact)
    trace_artifact.add_argument("--path", required=True)
    trace_artifact.set_defaults(func=cmd_trace_artifact)

    validate = subparsers.add_parser("validate", help="Validate graph structure, semantics, paths, and map freshness.")
    add_root(validate)
    validate.add_argument("--strict", action="store_true")
    validate.add_argument(
        "--scope",
        choices=("all", "active-route"),
        default="all",
        help="Apply strict warning failure globally (default) or only to the current progression route.",
    )
    validate.set_defaults(func=cmd_validate)

    render = subparsers.add_parser("render-map", help="Atomically render RESEARCH_MAP.md and migrate v1 when needed.")
    add_root(render)
    render.add_argument("--external-map", action="append", default=[])
    render.set_defaults(func=cmd_render_map)

    mission = subparsers.add_parser("mission", help="Print the user-visible mission board projection.")
    add_root(mission)
    mission.add_argument("--format", choices=("json", "markdown"), default="json")
    mission.set_defaults(func=cmd_mission)

    render_status_parser = subparsers.add_parser("render-status", help="Render STATUS.md from the mission board.")
    add_root(render_status_parser)
    render_status_parser.set_defaults(func=cmd_render_status)

    status = subparsers.add_parser("status", help="Print graph and map status as JSON.")
    add_root(status)
    status.add_argument("--json", action="store_true", help="Deprecated no-op; JSON is always emitted.")
    status.set_defaults(func=cmd_status)

    migrate = subparsers.add_parser("migrate", help="Migrate graph v1 to v2 with a preserved backup.")
    add_root(migrate)
    add_render_options(migrate)
    migrate.add_argument("--dry-run", action="store_true")
    migrate.add_argument("--external-map", action="append", default=[])
    migrate.set_defaults(func=cmd_migrate)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except CliError as exc:
        print(
            json.dumps({"ok": False, "error": str(exc), "details": exc.details}, ensure_ascii=False, indent=2),
            file=sys.stderr,
        )
        return exc.code
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 1


if __name__ == "__main__":
    configure_text_streams()
    raise SystemExit(main())
