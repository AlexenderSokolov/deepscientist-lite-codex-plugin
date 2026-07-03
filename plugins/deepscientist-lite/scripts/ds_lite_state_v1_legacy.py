#!/usr/bin/env python3
# Preserved v1 implementation. The supported entry point is ds_lite_state.py.
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "ds-lite.graph.v1"
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


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def slugify(value: str, fallback: str = "node") -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    return slug or fallback


def state_path(root: Path) -> Path:
    return root / "research" / "state" / "graph.json"


def rel_path(root: Path, value: str | None) -> str:
    if not value:
        return ""
    raw = value.strip()
    if not raw:
        return ""
    path = Path(raw)
    if path.is_absolute():
        try:
            return path.resolve().relative_to(root.resolve()).as_posix()
        except ValueError:
            return path.as_posix()
    return raw.replace("\\", "/")


def ensure_dirs(root: Path) -> None:
    for item in ("research/state", "research/memory", "research/artifacts"):
        (root / item).mkdir(parents=True, exist_ok=True)


def write_if_missing(path: Path, content: str) -> bool:
    if path.exists():
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return True


def new_graph(project_id: str, title: str, question: str) -> dict[str, Any]:
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
    return {
        "schema_version": SCHEMA_VERSION,
        "project": {"id": project_id, "title": title},
        "root_node_id": root_node["id"],
        "active_node_id": root_node["id"],
        "nodes": {root_node["id"]: root_node},
        "adjacency": {root_node["id"]: []},
    }


def read_optional_text(path_value: str) -> str:
    if not path_value:
        return ""
    return Path(path_value).read_text(encoding="utf-8").strip()


def load_graph(root: Path) -> dict[str, Any]:
    path = state_path(root)
    if not path.exists():
        raise SystemExit(f"State graph not found: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid JSON in {path}: {exc}") from exc


def save_graph(root: Path, graph: dict[str, Any]) -> None:
    ensure_dirs(root)
    state_path(root).write_text(json.dumps(graph, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def require_node(graph: dict[str, Any], node_id: str) -> dict[str, Any]:
    node = graph.get("nodes", {}).get(node_id)
    if not node:
        raise SystemExit(f"Unknown node id: {node_id}")
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
        raise SystemExit(f"Invalid edge relation: {relation}")
    require_node(graph, source)
    require_node(graph, target)
    edge = {
        "to": target,
        "relation": relation,
        "reason": reason,
        "artifact_path": artifact_path,
    }
    graph.setdefault("adjacency", {}).setdefault(source, [])
    if edge in graph["adjacency"][source]:
        return False
    graph["adjacency"][source].append(edge)
    return True


def validate_graph(graph: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if graph.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    if not isinstance(graph.get("project"), dict):
        errors.append("project must be an object")
    nodes = graph.get("nodes")
    adjacency = graph.get("adjacency")
    if not isinstance(nodes, dict):
        errors.append("nodes must be an object")
        nodes = {}
    if not isinstance(adjacency, dict):
        errors.append("adjacency must be an object")
        adjacency = {}

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
        for list_field in ("artifact_paths", "memory_paths", "evidence_paths"):
            if not isinstance(node.get(list_field), list):
                errors.append(f"node {node_id} field {list_field} must be a list")

    for special in ("root_node_id", "active_node_id"):
        node_id = graph.get(special)
        if node_id and node_id not in nodes:
            errors.append(f"{special} references missing node {node_id}")

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
            if target not in nodes:
                errors.append(f"edge {source}[{index}] points to missing node {target}")
            if edge.get("relation") not in EDGE_RELATIONS:
                errors.append(f"edge {source}[{index}] has invalid relation {edge.get('relation')}")
            for field in ("reason", "artifact_path"):
                if field not in edge:
                    errors.append(f"edge {source}[{index}] missing {field}")

    return errors


def find_route(graph: dict[str, Any], start: str, target: str) -> list[str]:
    if not start or not target:
        return []
    if start == target:
        return [start]
    adjacency = graph.get("adjacency", {})
    seen = {start}
    queue: deque[tuple[str, list[str]]] = deque([(start, [start])])
    while queue:
        node_id, path = queue.popleft()
        for edge in adjacency.get(node_id, []):
            child = edge.get("to")
            if not child or child in seen:
                continue
            if child == target:
                return path + [child]
            seen.add(child)
            queue.append((child, path + [child]))
    return []


def markdown_escape(value: Any) -> str:
    text = str(value or "")
    return text.replace("|", "\\|").replace("\n", " ")


def mermaid_id(node_id: str) -> str:
    return "n_" + re.sub(r"[^a-zA-Z0-9_]", "_", node_id)


def render_map(root: Path, graph: dict[str, Any]) -> Path:
    project = graph.get("project", {})
    nodes = graph.get("nodes", {})
    adjacency = graph.get("adjacency", {})
    active = graph.get("active_node_id", "")
    root_id = graph.get("root_node_id", "")
    route = find_route(graph, root_id, active) if active else []

    lines: list[str] = []
    lines.append(f"# Research Map: {project.get('title') or project.get('id') or 'Untitled Project'}")
    lines.append("")
    lines.append(f"- Schema: `{graph.get('schema_version')}`")
    lines.append(f"- Project id: `{project.get('id', '')}`")
    lines.append(f"- Root node: `{root_id}`")
    lines.append(f"- Active node: `{active}`")
    lines.append(f"- Last rendered: `{utc_now()}`")
    lines.append("")
    lines.append("## Active Route")
    lines.append("")
    if route:
        for node_id in route:
            node = nodes.get(node_id, {})
            lines.append(f"- `{node_id}` - {node.get('kind', '')}: {node.get('title', '')} [{node.get('status', '')}]")
    else:
        lines.append("- No route found from root to active node.")
    lines.append("")
    lines.append("## Graph")
    lines.append("")
    lines.append("```mermaid")
    lines.append("graph TD")
    if not nodes:
        lines.append('  empty["No nodes"]')
    for node_id, node in nodes.items():
        label = f"{node.get('kind', '')}: {node.get('title', '')} ({node.get('status', '')})".replace('"', "'")
        lines.append(f'  {mermaid_id(node_id)}["{label}"]')
    for source, edges in adjacency.items():
        for edge in edges:
            target = edge.get("to", "")
            relation = edge.get("relation", "")
            if source in nodes and target in nodes:
                lines.append(f"  {mermaid_id(source)} -->|{relation}| {mermaid_id(target)}")
    lines.append("```")
    lines.append("")
    lines.append("## Nodes")
    lines.append("")
    lines.append("| id | kind | status | title | artifacts |")
    lines.append("| --- | --- | --- | --- | --- |")
    for node_id, node in nodes.items():
        artifacts = ", ".join(node.get("artifact_paths", []))
        lines.append(
            f"| `{markdown_escape(node_id)}` | {markdown_escape(node.get('kind'))} | "
            f"{markdown_escape(node.get('status'))} | {markdown_escape(node.get('title'))} | "
            f"{markdown_escape(artifacts)} |"
        )
    lines.append("")
    lines.append("## Edges")
    lines.append("")
    lines.append("| from | relation | to | reason | artifact |")
    lines.append("| --- | --- | --- | --- | --- |")
    for source, edges in adjacency.items():
        for edge in edges:
            lines.append(
                f"| `{markdown_escape(source)}` | {markdown_escape(edge.get('relation'))} | "
                f"`{markdown_escape(edge.get('to'))}` | {markdown_escape(edge.get('reason'))} | "
                f"{markdown_escape(edge.get('artifact_path'))} |"
            )

    output = root / "RESEARCH_MAP.md"
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return output


def cmd_init(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    ensure_dirs(root)
    graph_file = state_path(root)
    title_text = read_optional_text(args.title_file) or args.title or root.name
    question_text = read_optional_text(args.question_file) or args.question or ""
    if graph_file.exists():
        graph = load_graph(root)
        if args.render:
            render_map(root, graph)
        emit({"ok": True, "status": "exists", "graph": str(graph_file)})
        return 0

    title = title_text
    project_id = args.project_id or slugify(title, fallback="ds-lite-project")
    graph = new_graph(project_id=project_id, title=title, question=question_text)
    save_graph(root, graph)

    today = datetime.now().strftime("%Y-%m-%d")
    write_if_missing(
        root / "PROJECT.md",
        f"""# {title}

## Background

TBD.

## Core Question

{question_text or 'TBD.'}

## Hypotheses

- TBD.

## Inputs

- Code:
- Data:
- Papers:
- Baselines:

## Workflow

1. Intake and project memory
2. Scout literature, datasets, benchmarks, and baselines
3. Generate candidate ideas
4. Run reproducible experiments
5. Analyze evidence and write final claims

## Run Commands

- Research: `bash run_research.sh`
- Experiment: `bash run_experiment.sh`
- Analysis: `bash run_analysis.sh`

## Acceptance Criteria

- TBD.

## Design Decisions

- Use DeepScientist Lite file protocol for lightweight research-state tracking.

## Deprecated Ideas

- None yet.
""",
    )
    write_if_missing(
        root / "STATUS.md",
        f"""# Status

## Current Node

- Active node: `intake-root`
- Stage: intake
- Status: active

## Current Summary

{question_text or 'Project initialized.'}

## Blockers

- None recorded.

## Next Action

Run scouting to identify baselines, metrics, and first validation route.

## Last Updated

{today}
""",
    )
    write_if_missing(root / "run_research.sh", "#!/usr/bin/env bash\nset -euo pipefail\n\necho \"Add research scouting commands here.\"\n")
    write_if_missing(root / "run_experiment.sh", "#!/usr/bin/env bash\nset -euo pipefail\n\necho \"Add experiment commands here.\"\n")
    write_if_missing(root / "run_analysis.sh", "#!/usr/bin/env bash\nset -euo pipefail\n\necho \"Add analysis commands here.\"\n")
    render_map(root, graph)
    emit({"ok": True, "status": "created", "graph": str(graph_file), "active_node_id": "intake-root"})
    return 0


def cmd_add_node(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    graph = load_graph(root)
    if args.kind not in NODE_KINDS:
        raise SystemExit(f"Invalid node kind: {args.kind}")
    if args.status not in NODE_STATUSES:
        raise SystemExit(f"Invalid node status: {args.status}")
    node_id = args.id or make_node_id(graph, args.kind, args.title)
    if node_id in graph.get("nodes", {}):
        raise SystemExit(f"Node already exists: {node_id}")
    now = utc_now()
    node = {
        "id": node_id,
        "kind": args.kind,
        "status": args.status,
        "title": args.title,
        "summary": args.summary or "",
        "artifact_paths": [rel_path(root, p) for p in args.artifact_path],
        "memory_paths": [rel_path(root, p) for p in args.memory_path],
        "evidence_paths": [rel_path(root, p) for p in args.evidence_path],
        "created_at": now,
        "updated_at": now,
    }
    graph.setdefault("nodes", {})[node_id] = node
    graph.setdefault("adjacency", {}).setdefault(node_id, [])
    if not graph.get("root_node_id"):
        graph["root_node_id"] = node_id
    if args.parent:
        add_edge_obj(
            graph,
            source=args.parent,
            target=node_id,
            relation=args.relation,
            reason=args.reason or f"{args.relation} to {node_id}",
            artifact_path=rel_path(root, args.edge_artifact_path),
        )
    if args.active:
        for item in graph.get("nodes", {}).values():
            if item.get("status") == "active" and item.get("id") != node_id:
                item["status"] = "done"
                item["updated_at"] = now
        node["status"] = "active"
        graph["active_node_id"] = node_id
    save_graph(root, graph)
    if args.render:
        render_map(root, graph)
    emit({"ok": True, "node_id": node_id, "active_node_id": graph.get("active_node_id", "")})
    return 0


def cmd_add_edge(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    graph = load_graph(root)
    added = add_edge_obj(
        graph,
        source=args.source,
        target=args.target,
        relation=args.relation,
        reason=args.reason or "",
        artifact_path=rel_path(root, args.artifact_path),
    )
    save_graph(root, graph)
    if args.render:
        render_map(root, graph)
    emit({"ok": True, "added": added, "from": args.source, "to": args.target, "relation": args.relation})
    return 0


def cmd_link_artifact(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    graph = load_graph(root)
    node = require_node(graph, args.node)
    path = rel_path(root, args.path)
    append_unique(node.setdefault("artifact_paths", []), path)
    node["updated_at"] = utc_now()
    save_graph(root, graph)
    if args.render:
        render_map(root, graph)
    emit({"ok": True, "node_id": args.node, "artifact_path": path})
    return 0


def cmd_set_active(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    graph = load_graph(root)
    target = require_node(graph, args.node)
    now = utc_now()
    for node in graph.get("nodes", {}).values():
        if node.get("status") == "active" and node.get("id") != args.node:
            node["status"] = "done"
            node["updated_at"] = now
    target["status"] = "active"
    target["updated_at"] = now
    graph["active_node_id"] = args.node
    save_graph(root, graph)
    if args.render:
        render_map(root, graph)
    emit({"ok": True, "active_node_id": args.node})
    return 0


def cmd_trace(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    graph = load_graph(root)
    target = args.node or graph.get("active_node_id", "")
    require_node(graph, target)
    route = find_route(graph, graph.get("root_node_id", ""), target)
    payload = {
        "ok": bool(route),
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
                print(
                    f"{index}. `{node_id}` - {node.get('kind', '')}: "
                    f"{node.get('title', '')} [{node.get('status', '')}]"
                )
        else:
            print("No route found from root to target node.")
    else:
        emit(payload)
    return 0 if route else 2


def cmd_trace_artifact(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    graph = load_graph(root)
    query = rel_path(root, args.path)
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
    emit({"ok": True, "path": query, "count": len(matches), "nodes": matches})
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    graph = load_graph(root)
    errors = validate_graph(graph)
    emit({"ok": not errors, "errors": errors, "graph": str(state_path(root))})
    return 0 if not errors else 1


def cmd_render_map(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    graph = load_graph(root)
    output = render_map(root, graph)
    emit({"ok": True, "path": str(output)})
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    graph = load_graph(root)
    active_id = graph.get("active_node_id", "")
    active = graph.get("nodes", {}).get(active_id, {})
    emit(
        {
            "ok": True,
            "project": graph.get("project", {}),
            "root_node_id": graph.get("root_node_id", ""),
            "active_node_id": active_id,
            "active": active,
            "node_count": len(graph.get("nodes", {})),
            "edge_count": sum(len(edges) for edges in graph.get("adjacency", {}).values() if isinstance(edges, list)),
        }
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage DeepScientist Lite research state graphs.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    def add_root(sub: argparse.ArgumentParser) -> None:
        sub.add_argument("--root", default=".", help="Project root. Defaults to current directory.")

    init = subparsers.add_parser("init", help="Initialize DS Lite files in a project.")
    add_root(init)
    init.add_argument("--title", default="", help="Project title.")
    init.add_argument("--title-file", default="", help="UTF-8 text file containing the project title.")
    init.add_argument("--project-id", default="", help="Stable project id.")
    init.add_argument("--question", default="", help="Initial research question.")
    init.add_argument("--question-file", default="", help="UTF-8 text file containing the initial research question.")
    init.add_argument("--render", action="store_true", default=True, help="Render RESEARCH_MAP.md.")
    init.set_defaults(func=cmd_init)

    add_node = subparsers.add_parser("add-node", help="Add a graph node.")
    add_root(add_node)
    add_node.add_argument("--id", default="", help="Optional explicit node id.")
    add_node.add_argument("--kind", required=True, choices=sorted(NODE_KINDS))
    add_node.add_argument("--status", default="proposed", choices=sorted(NODE_STATUSES))
    add_node.add_argument("--title", required=True)
    add_node.add_argument("--summary", default="")
    add_node.add_argument("--parent", default="", help="Parent/source node id for the edge.")
    add_node.add_argument("--relation", default="next", choices=sorted(EDGE_RELATIONS))
    add_node.add_argument("--reason", default="")
    add_node.add_argument("--edge-artifact-path", default="")
    add_node.add_argument("--artifact-path", action="append", default=[])
    add_node.add_argument("--memory-path", action="append", default=[])
    add_node.add_argument("--evidence-path", action="append", default=[])
    add_node.add_argument("--active", action="store_true")
    add_node.add_argument("--render", action="store_true")
    add_node.set_defaults(func=cmd_add_node)

    add_edge = subparsers.add_parser("add-edge", help="Add an edge between existing nodes.")
    add_root(add_edge)
    add_edge.add_argument("--from", dest="source", required=True)
    add_edge.add_argument("--to", dest="target", required=True)
    add_edge.add_argument("--relation", required=True, choices=sorted(EDGE_RELATIONS))
    add_edge.add_argument("--reason", default="")
    add_edge.add_argument("--artifact-path", default="")
    add_edge.add_argument("--render", action="store_true")
    add_edge.set_defaults(func=cmd_add_edge)

    link_artifact = subparsers.add_parser("link-artifact", help="Attach an artifact path to a node.")
    add_root(link_artifact)
    link_artifact.add_argument("--node", required=True)
    link_artifact.add_argument("--path", required=True)
    link_artifact.add_argument("--render", action="store_true")
    link_artifact.set_defaults(func=cmd_link_artifact)

    set_active = subparsers.add_parser("set-active", help="Set active node.")
    add_root(set_active)
    set_active.add_argument("--node", required=True)
    set_active.add_argument("--render", action="store_true")
    set_active.set_defaults(func=cmd_set_active)

    trace = subparsers.add_parser("trace", help="Trace route from root to a node.")
    add_root(trace)
    trace.add_argument("--node", default="", help="Target node id. Defaults to active node.")
    trace.add_argument("--format", choices=("json", "markdown"), default="json", help="Output format.")
    trace.set_defaults(func=cmd_trace)

    trace_artifact = subparsers.add_parser("trace-artifact", help="Find nodes linked to an artifact path.")
    add_root(trace_artifact)
    trace_artifact.add_argument("--path", required=True)
    trace_artifact.set_defaults(func=cmd_trace_artifact)

    validate = subparsers.add_parser("validate", help="Validate graph consistency.")
    add_root(validate)
    validate.set_defaults(func=cmd_validate)

    render = subparsers.add_parser("render-map", help="Render RESEARCH_MAP.md.")
    add_root(render)
    render.set_defaults(func=cmd_render_map)

    status = subparsers.add_parser("status", help="Print graph status.")
    add_root(status)
    status.add_argument("--json", action="store_true", help="Print JSON status. This is the default output.")
    status.set_defaults(func=cmd_status)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
