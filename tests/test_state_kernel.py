from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
STATE_SCRIPT = REPO_ROOT / "plugins" / "deepscientist-lite" / "scripts" / "ds_lite_state.py"
SCRIPT_DIR = STATE_SCRIPT.parent


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def run_cli(root: Path, *args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    command = [sys.executable, str(STATE_SCRIPT), *args, "--root", str(root)]
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    return subprocess.run(command, cwd=REPO_ROOT, text=True, encoding="utf-8", capture_output=True, env=merged_env)


def parse_output(result: subprocess.CompletedProcess[str]) -> dict:
    if not result.stdout.strip():
        raise AssertionError(f"command produced no JSON stdout\nstderr: {result.stderr}")
    return json.loads(result.stdout)


def make_v1_graph(root: Path, evidence_path: str = "PROJECT.md") -> None:
    now = utc_now()
    graph = {
        "schema_version": "ds-lite.graph.v1",
        "project": {"id": "legacy", "title": "Legacy Project"},
        "root_node_id": "intake-root",
        "active_node_id": "intake-root",
        "nodes": {
            "intake-root": {
                "id": "intake-root",
                "kind": "intake",
                "status": "active",
                "title": "Legacy intake",
                "summary": "Legacy graph",
                "artifact_paths": [],
                "memory_paths": [],
                "evidence_paths": [evidence_path],
                "created_at": now,
                "updated_at": now,
            }
        },
        "adjacency": {"intake-root": []},
    }
    graph_path = root / "research" / "state" / "graph.json"
    graph_path.parent.mkdir(parents=True, exist_ok=True)
    graph_path.write_text(json.dumps(graph, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (root / "PROJECT.md").write_text("# Legacy\n", encoding="utf-8")


class StateKernelTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="ds lite 中文 "))
        result = run_cli(self.root, "init", "--title", "中文项目", "--question", "状态图是否可靠？")
        self.assertEqual(result.returncode, 0, result.stderr)

    def graph(self) -> dict:
        return json.loads((self.root / "research" / "state" / "graph.json").read_text(encoding="utf-8"))

    def write_artifact(self, relative: str, content: str = "# Evidence\n") -> None:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def add_node(self, node_id: str, parent: str = "intake-root", *, active: bool = False) -> subprocess.CompletedProcess[str]:
        relative = f"research/artifacts/{node_id}.md"
        self.write_artifact(relative)
        args = [
            "add-node",
            "--id",
            node_id,
            "--kind",
            "scout",
            "--parent",
            parent,
            "--relation",
            "next",
            "--title",
            node_id,
            "--artifact-path",
            relative,
        ]
        if active:
            args.append("--active")
        return run_cli(self.root, *args)

    def test_init_uses_v2_templates_and_unicode(self) -> None:
        graph = self.graph()
        self.assertEqual(graph["schema_version"], "ds-lite.graph.v2")
        self.assertEqual(graph["revision"], 0)
        self.assertEqual(graph["nodes"]["intake-root"]["summary"], "状态图是否可靠？")
        self.assertIn("# 中文项目", (self.root / "PROJECT.md").read_text(encoding="utf-8"))
        self.assertIn("- Revision: `0`", (self.root / "RESEARCH_MAP.md").read_text(encoding="utf-8"))

        western_root = Path(tempfile.mkdtemp(prefix="ds lite western console "))
        western = run_cli(
            western_root,
            "init",
            "--title",
            "中文项目",
            "--question",
            "状态图是否可靠？",
            env={"PYTHONUTF8": "0", "PYTHONIOENCODING": "cp1252"},
        )
        self.assertEqual(western.returncode, 0, western.stderr)
        western_graph = json.loads(
            (western_root / "research" / "state" / "graph.json").read_text(encoding="utf-8")
        )
        self.assertEqual(western_graph["nodes"]["intake-root"]["summary"], "状态图是否可靠？")

    def test_mutation_api_and_revision_conflict(self) -> None:
        self.write_artifact("research/artifacts/scout.md")
        added = run_cli(
            self.root,
            "add-node",
            "--id",
            "scout",
            "--kind",
            "scout",
            "--parent",
            "intake-root",
            "--title",
            "Scout",
            "--artifact-path",
            "research/artifacts/scout.md",
            "--active",
            "--expected-revision",
            "0",
        )
        self.assertEqual(added.returncode, 0, added.stderr)
        updated = run_cli(
            self.root,
            "update-node",
            "--node",
            "scout",
            "--summary",
            "Updated summary",
            "--expected-revision",
            "1",
        )
        self.assertEqual(updated.returncode, 0, updated.stderr)
        self.write_artifact("research/memory/scout.md")
        linked = run_cli(
            self.root,
            "link-path",
            "--node",
            "scout",
            "--type",
            "memory",
            "--path",
            "research/memory/scout.md",
            "--expected-revision",
            "2",
        )
        self.assertEqual(linked.returncode, 0, linked.stderr)
        conflict = run_cli(
            self.root,
            "set-status",
            "--node",
            "scout",
            "--status",
            "blocked",
            "--expected-revision",
            "1",
        )
        self.assertEqual(conflict.returncode, 4)
        self.assertEqual(self.graph()["revision"], 3)

    def test_progression_trace_ignores_supports_shortcut(self) -> None:
        self.assertEqual(self.add_node("scout").returncode, 0)
        self.write_artifact("research/artifacts/idea.md")
        idea = run_cli(
            self.root,
            "add-node",
            "--id",
            "idea",
            "--kind",
            "idea",
            "--parent",
            "scout",
            "--relation",
            "next",
            "--title",
            "Idea",
            "--artifact-path",
            "research/artifacts/idea.md",
            "--active",
        )
        self.assertEqual(idea.returncode, 0, idea.stderr)
        shortcut = run_cli(
            self.root,
            "add-edge",
            "--from",
            "intake-root",
            "--to",
            "idea",
            "--relation",
            "supports",
        )
        self.assertEqual(shortcut.returncode, 0, shortcut.stderr)
        progression = parse_output(run_cli(self.root, "trace", "--node", "idea"))
        all_edges = parse_output(run_cli(self.root, "trace", "--node", "idea", "--mode", "all"))
        self.assertEqual([item["id"] for item in progression["route"]], ["intake-root", "scout", "idea"])
        self.assertEqual([item["id"] for item in all_edges["route"]], ["intake-root", "idea"])

    def test_map_staleness_is_detected_and_repaired(self) -> None:
        self.write_artifact("research/artifacts/scout.md")
        result = run_cli(
            self.root,
            "add-node",
            "--id",
            "scout",
            "--kind",
            "scout",
            "--parent",
            "intake-root",
            "--title",
            "Scout",
            "--artifact-path",
            "research/artifacts/scout.md",
            "--no-render",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(parse_output(run_cli(self.root, "status"))["map_stale"])
        rendered = run_cli(self.root, "render-map")
        self.assertEqual(rendered.returncode, 0, rendered.stderr)
        self.assertFalse(parse_output(run_cli(self.root, "status"))["map_stale"])

    def test_semantic_validation_reports_conflict_and_unreachable_node(self) -> None:
        graph = self.graph()
        now = utc_now()
        graph["nodes"]["orphan"] = {
            "id": "orphan",
            "kind": "idea",
            "status": "active",
            "title": "Orphan",
            "summary": "Unreachable",
            "artifact_paths": [],
            "memory_paths": [],
            "evidence_paths": [],
            "created_at": now,
            "updated_at": now,
        }
        graph["adjacency"]["orphan"] = []
        (self.root / "research" / "state" / "graph.json").write_text(
            json.dumps(graph, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        result = run_cli(self.root, "validate")
        self.assertEqual(result.returncode, 1)
        payload = parse_output(result)
        self.assertTrue(any("multiple nodes" in item for item in payload["errors"]))
        self.assertTrue(any("unreachable" in item for item in payload["errors"]))

    def test_v1_migration_preserves_backup(self) -> None:
        root = Path(tempfile.mkdtemp(prefix="ds-lite-v1-"))
        make_v1_graph(root)
        result = run_cli(root, "migrate")
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = parse_output(result)
        self.assertTrue(Path(payload["backup"]).exists())
        migrated = json.loads((root / "research" / "state" / "graph.json").read_text(encoding="utf-8"))
        self.assertEqual(migrated["schema_version"], "ds-lite.graph.v2")
        self.assertEqual(migrated["revision"], 0)
        again = parse_output(run_cli(root, "migrate"))
        self.assertEqual(again["status"], "already-current")

    def test_first_v1_write_migrates_then_increments_revision(self) -> None:
        root = Path(tempfile.mkdtemp(prefix="ds-lite-v1-auto-"))
        make_v1_graph(root)
        artifact = root / "research" / "artifacts" / "scout.md"
        artifact.parent.mkdir(parents=True, exist_ok=True)
        artifact.write_text("# Scout\n", encoding="utf-8")
        result = run_cli(
            root,
            "add-node",
            "--id",
            "scout",
            "--kind",
            "scout",
            "--parent",
            "intake-root",
            "--title",
            "Scout",
            "--artifact-path",
            "research/artifacts/scout.md",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = parse_output(result)
        self.assertTrue(Path(payload["backup"]).exists())
        graph = json.loads((root / "research" / "state" / "graph.json").read_text(encoding="utf-8"))
        self.assertEqual(graph["schema_version"], "ds-lite.graph.v2")
        self.assertEqual(graph["revision"], 1)

    def test_v1_external_path_requires_explicit_alias(self) -> None:
        root = Path(tempfile.mkdtemp(prefix="ds-lite-v1-external-"))
        external_root = Path(tempfile.mkdtemp(prefix="ds-lite-data-"))
        external_file = external_root / "input.txt"
        external_file.write_text("data\n", encoding="utf-8")
        make_v1_graph(root, str(external_file))
        blocked = run_cli(root, "migrate", "--dry-run")
        self.assertEqual(blocked.returncode, 5)
        blocked_write = run_cli(root, "set-status", "--node", "intake-root", "--status", "blocked")
        self.assertEqual(blocked_write.returncode, 5)
        self.assertFalse(list((root / "research" / "state").glob("graph.v1.*.json")))
        migrated = run_cli(root, "migrate", "--external-map", f"data={external_root}")
        self.assertEqual(migrated.returncode, 0, migrated.stderr)
        graph = json.loads((root / "research" / "state" / "graph.json").read_text(encoding="utf-8"))
        self.assertEqual(graph["nodes"]["intake-root"]["evidence_paths"], ["external://data/input.txt"])
        unresolved = run_cli(root, "validate", "--strict")
        self.assertEqual(unresolved.returncode, 1)
        resolved = run_cli(root, "validate", "--strict", env={"DS_LITE_EXTERNAL_DATA": str(external_root)})
        self.assertEqual(resolved.returncode, 0, resolved.stderr)

    def test_foreign_windows_absolute_path_is_never_treated_as_relative(self) -> None:
        root = Path(tempfile.mkdtemp(prefix="ds-lite-v1-foreign-path-"))
        make_v1_graph(root, r"C:\private\dataset\input.txt")
        result = run_cli(root, "migrate", "--dry-run")
        self.assertEqual(result.returncode, 5)

    def test_new_writes_reject_external_absolute_paths_as_data_errors(self) -> None:
        external_root = Path(tempfile.mkdtemp(prefix="ds-lite-new-external-"))
        external_file = external_root / "result.json"
        external_file.write_text("{}\n", encoding="utf-8")
        result = run_cli(
            self.root,
            "link-path",
            "--node",
            "intake-root",
            "--type",
            "evidence",
            "--path",
            str(external_file),
        )
        self.assertEqual(result.returncode, 1)
        self.assertEqual(self.graph()["revision"], 0)

    def test_concurrent_writers_do_not_lose_nodes(self) -> None:
        processes = []
        for index in range(6):
            command = [
                sys.executable,
                str(STATE_SCRIPT),
                "add-node",
                "--root",
                str(self.root),
                "--id",
                f"branch-{index}",
                "--kind",
                "idea",
                "--parent",
                "intake-root",
                "--relation",
                "branch",
                "--title",
                f"Branch {index}",
                "--no-render",
            ]
            processes.append(
                subprocess.Popen(
                    command,
                    cwd=REPO_ROOT,
                    text=True,
                    encoding="utf-8",
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
            )
        results = [process.communicate(timeout=20) + (process.returncode,) for process in processes]
        for stdout, stderr, returncode in results:
            self.assertEqual(returncode, 0, f"stdout={stdout}\nstderr={stderr}")
        graph = self.graph()
        self.assertEqual(graph["revision"], 6)
        for index in range(6):
            self.assertIn(f"branch-{index}", graph["nodes"])

    def test_lock_timeout_returns_exit_code_three(self) -> None:
        holder_code = (
            "import sys,time; "
            f"sys.path.insert(0, {str(SCRIPT_DIR)!r}); "
            "import ds_lite_state as state; "
            f"root=state.Path({str(self.root)!r}); "
            "lock=state.graph_lock(root, timeout=1); lock.__enter__(); "
            "print('locked', flush=True); time.sleep(2); lock.__exit__(None,None,None)"
        )
        holder = subprocess.Popen(
            [sys.executable, "-c", holder_code],
            cwd=REPO_ROOT,
            text=True,
            encoding="utf-8",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        try:
            self.assertEqual(holder.stdout.readline().strip(), "locked")
            self.write_artifact("research/artifacts/locked.md")
            result = run_cli(
                self.root,
                "add-node",
                "--id",
                "locked",
                "--kind",
                "scout",
                "--parent",
                "intake-root",
                "--title",
                "Locked",
                env={"DS_LITE_LOCK_TIMEOUT": "0.2"},
            )
            self.assertEqual(result.returncode, 3, result.stderr)
        finally:
            holder.wait(timeout=5)
            if holder.stdout:
                holder.stdout.close()
            if holder.stderr:
                holder.stderr.close()


if __name__ == "__main__":
    unittest.main()
