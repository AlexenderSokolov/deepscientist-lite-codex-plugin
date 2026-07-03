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

SCHEMA_V1 = "ds-lite.graph.v1"
SCHEMA_VERSION = "ds-lite.graph.v2"
NODE_KINDS = {
    "intake",
    "scout",
    "idea",
    "experiment",
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
    for item in ("research/state", "research/memory", "research/artifacts"):
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


def validate_graph(root: Path, graph: dict[str, Any], check_paths: bool = True) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    schema = graph.get("schema_version")
    if schema not in {SCHEMA_V1, SCHEMA_VERSION}:
        errors.append(f"schema_version must be {SCHEMA_V1} or {SCHEMA_VERSION}")
    if schema == SCHEMA_V1:
        warnings.append("graph uses ds-lite.graph.v1; migrate before the next state change")
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
                    warnings.append(f"node {node_id} external path cannot be resolved: {path_problem}")
                    continue
                if resolved is not None and not resolved.exists():
                    message = f"node {node_id} {list_field} path does not exist: {value}"
                    if list_field in {"artifact_paths", "memory_paths"} or node.get("status") == "done":
                        errors.append(message)
                    else:
                        warnings.append(message)

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
                        warnings.append(f"edge {source}[{index}] external path cannot be resolved: {path_problem}")
                    elif resolved is not None and not resolved.exists():
                        errors.append(f"edge {source}[{index}] artifact_path does not exist: {artifact_path}")

    for node_id in nodes:
        if node_id == root_id:
            continue
        if not find_route(graph, root_id, node_id, mode="progression"):
            errors.append(f"node {node_id} is unreachable from root through progression edges")
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
        values = {"project_title": title, "question": question or "TBD.", "date": today}
        created = []
        for relative, template_name in (
            ("PROJECT.md", "PROJECT.md"),
            ("STATUS.md", "STATUS.md"),
            ("run_research.sh", "run_research.sh"),
            ("run_experiment.sh", "run_experiment.sh"),
            ("run_analysis.sh", "run_analysis.sh"),
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
        node["updated_at"] = utc_now()
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
        node["updated_at"] = utc_now()
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
            node["updated_at"] = timestamp
    target["status"] = "active"
    target["updated_at"] = timestamp
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
            node["updated_at"] = utc_now()
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
    errors, warnings = validate_graph(root, graph, check_paths=True)
    if map_is_stale(root, graph):
        warnings.append("RESEARCH_MAP.md is missing or stale; run render-map")
    ok = not errors and (not args.strict or not warnings)
    emit(
        {
            "ok": ok,
            "strict": args.strict,
            "schema_version": graph.get("schema_version"),
            "revision": graph.get("revision", 0),
            "errors": errors,
            "warnings": warnings,
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
    validate.set_defaults(func=cmd_validate)

    render = subparsers.add_parser("render-map", help="Atomically render RESEARCH_MAP.md and migrate v1 when needed.")
    add_root(render)
    render.add_argument("--external-map", action="append", default=[])
    render.set_defaults(func=cmd_render_map)

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
