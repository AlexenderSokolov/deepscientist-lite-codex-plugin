from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path
from string import Template

REPO_ROOT = Path(__file__).resolve().parents[1]
STATE_SCRIPT = REPO_ROOT / "plugins" / "deepscientist-lite" / "scripts" / "ds_lite_state.py"
EVIDENCE_SCRIPT = REPO_ROOT / "plugins" / "deepscientist-lite" / "scripts" / "ds_lite_evidence.py"
SCRIPT_DIR = STATE_SCRIPT.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import ds_lite_protocol
import ds_lite_iteration

REVIEW_RESULT_TEMPLATE = (
    REPO_ROOT
    / "plugins"
    / "deepscientist-lite"
    / "assets"
    / "templates"
    / "research"
    / "artifacts"
    / "review-result.json"
)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def run_cli(root: Path, *args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    command = [sys.executable, str(STATE_SCRIPT), *args, "--root", str(root)]
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    return subprocess.run(
        command,
        cwd=REPO_ROOT,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        env=merged_env,
    )


def parse_output(result: subprocess.CompletedProcess[str]) -> dict:
    if not result.stdout.strip():
        raise AssertionError(f"command produced no JSON stdout\nstderr: {result.stderr}")
    return json.loads(result.stdout)


def portable_bash() -> str | None:
    """Prefer Git Bash on Windows; System32 bash may launch an unrelated WSL host."""
    candidate: Path | None = None
    if sys.platform == "win32":
        completed = subprocess.run(
            ["git", "--exec-path"],
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
        )
        if completed.returncode == 0:
            git_exec = Path(completed.stdout.strip())
            if len(git_exec.parents) >= 3:
                candidate = git_exec.parents[2] / "bin" / "bash.exe"
        if candidate is None or not candidate.is_file():
            return None
    else:
        resolved = shutil.which("bash")
        candidate = Path(resolved) if resolved else None
    if candidate is None:
        return None
    try:
        capability = subprocess.run(
            [str(candidate), "--version"],
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return str(candidate) if capability.returncode == 0 else None


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

    def write_evidence_manifest(
        self,
        node_id: str,
        run_id: str = "run-01",
        verification_status: str = "pass",
        metrics: list[dict] | None = None,
        budget: dict | None = None,
        exit_code: int = 0,
    ) -> str:
        metrics = metrics or [{"name": "accuracy", "direction": "max", "threshold": 0.8}]
        budget = budget or {"value": 1, "unit": "run"}
        fixture_dir = self.root / "test-inputs" / run_id
        fixture_dir.mkdir(parents=True, exist_ok=True)
        contract_input = fixture_dir / "contract.json"
        contract_input.write_text(
            json.dumps(
                {
                    "schema_version": "ds-lite.experiment-contract.v1",
                    "run_id": run_id,
                    "node_id": node_id,
                    "hypothesis": "Smoke hypothesis.",
                    "command": "python smoke.py",
                    "cwd": ".",
                    "inputs": [],
                    "metrics": metrics,
                    "seeds": [0],
                    "budget": budget,
                    "expected_outputs": [],
                    "failure_interpretation": "Failure blocks claim promotion.",
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        initialized = subprocess.run(
            [
                sys.executable,
                str(EVIDENCE_SCRIPT),
                "init",
                "--root",
                str(self.root),
                "--run-id",
                run_id,
                "--contract",
                str(contract_input),
            ],
            cwd=REPO_ROOT,
            text=True,
            encoding="utf-8",
            capture_output=True,
        )
        self.assertEqual(initialized.returncode, 0, initialized.stdout + initialized.stderr)

        stdout_path = fixture_dir / "stdout.log"
        stderr_path = fixture_dir / "stderr.log"
        metrics_path = fixture_dir / "metrics.json"
        environment_path = fixture_dir / "environment.json"
        stdout_path.write_text("completed\n", encoding="utf-8")
        stderr_path.write_text("", encoding="utf-8")
        metric_values: dict[str, float] = {}
        for metric in metrics:
            direction = metric["direction"]
            threshold = float(metric.get("threshold", 0.0))
            if direction == "max":
                metric_values[metric["name"]] = threshold + 0.1
            elif direction == "min":
                metric_values[metric["name"]] = threshold - 0.1
            else:
                metric_values[metric["name"]] = threshold
        metrics_path.write_text(json.dumps(metric_values, indent=2) + "\n", encoding="utf-8")
        environment_path.write_text(
            json.dumps(
                {
                    "schema_version": "ds-lite.environment.v1",
                    "python": sys.version.split()[0],
                    "platform": sys.platform,
                    "packages": [],
                    "container": "not-applicable",
                    "hardware": "test",
                    "notes": "sanitized",
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        finalized = subprocess.run(
            [
                sys.executable,
                str(EVIDENCE_SCRIPT),
                "finalize",
                "--root",
                str(self.root),
                "--run-id",
                run_id,
                "--exit-code",
                str(exit_code),
                "--stdout",
                str(stdout_path),
                "--stderr",
                str(stderr_path),
                "--metrics",
                str(metrics_path),
                "--environment",
                str(environment_path),
            ],
            cwd=REPO_ROOT,
            text=True,
            encoding="utf-8",
            capture_output=True,
        )
        self.assertEqual(finalized.returncode, 0, finalized.stdout + finalized.stderr)
        verified = subprocess.run(
            [
                sys.executable,
                str(EVIDENCE_SCRIPT),
                "verify",
                "--root",
                str(self.root),
                "--run-id",
                run_id,
                "--strict",
            ],
            cwd=REPO_ROOT,
            text=True,
            encoding="utf-8",
            capture_output=True,
        )
        self.assertEqual(verified.returncode, 0, verified.stdout + verified.stderr)

        relative = f"research/evidence/{run_id}/manifest.json"
        if verification_status != "pass":
            manifest_path = self.root / relative
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["verification"]["status"] = verification_status
            manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        return relative

    def write_work_unit(
        self,
        *,
        profile_id: str = "core-planning",
        evidence_requirements: list[dict] | None = None,
        evidence_refs: list[str] | None = None,
        extensions: dict | None = None,
        **updates: object,
    ) -> dict:
        payload = {
            "schema_version": "ds-lite.work-unit.v1",
            "work_unit_id": "work-main",
            "title": "Current bounded work",
            "goal": "Advance one evidence-bounded research step.",
            "execution_mode": "none",
            "profile_id": profile_id,
            "state": "active",
            "prerequisites": [],
            "required_capabilities": ["read"],
            "evidence_requirements": evidence_requirements or [],
            "evidence_refs": evidence_refs or [],
            "resource_limits": [{"dimension": "actions", "unit": "count", "value": 1}],
            "subjects": [{"kind": "artifact", "id": "project-contract", "query_ref": "PROJECT.md"}],
            "active_iteration_ref": "",
            "extensions": extensions or {},
        }
        payload.update(updates)
        path = self.root / "research" / "work-unit.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return payload

    def evidence_refs_digest(self, refs: list[str]) -> str:
        records = []
        for ref in sorted(refs):
            records.append({"path": ref, "sha256": hashlib.sha256((self.root / ref).read_bytes()).hexdigest()})
        canonical = json.dumps(records, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(canonical).hexdigest()

    def write_review_result(
        self,
        *,
        review_node_id: str,
        reviewed_node_id: str,
        evidence_refs: list[str],
        verdict: str = "pass",
        claim_assessment: str = "supportable",
        extensions: dict | None = None,
        **updates: object,
    ) -> str:
        work_unit = json.loads((self.root / "research" / "work-unit.json").read_text(encoding="utf-8"))
        artifact_ref = f"research/artifacts/{review_node_id}.md"
        channels = {"integrity": "pass"}
        if verdict == "fail":
            channels = {"integrity": "fail"}
        elif verdict == "needs-human":
            channels = {"integrity": "needs-human"}
        payload = {
            "schema_version": "ds-lite.review-result.v1",
            "review_id": review_node_id,
            "work_unit_id": work_unit["work_unit_id"],
            "profile_id": work_unit["profile_id"],
            "review_node_id": review_node_id,
            "reviewed_node_id": reviewed_node_id,
            "reviewed_evidence_refs": evidence_refs,
            "evidence_validator": "ds-lite.evidence.v1",
            "evidence_digest": self.evidence_refs_digest(evidence_refs),
            "verdict": verdict,
            "claim_assessment": claim_assessment,
            "channels": channels,
            "limitations": [],
            "review_artifact_ref": artifact_ref,
            "completed_at": utc_now(),
            "extensions": extensions or {},
        }
        payload.update(updates)
        relative = f"research/artifacts/{review_node_id}.json"
        (self.root / relative).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return relative

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

    def add_experiment_node(self, node_id: str, manifest: str = "", *, active: bool = True) -> None:
        artifact = f"research/artifacts/{node_id}.md"
        self.write_artifact(artifact)
        args = [
            "add-node",
            "--id",
            node_id,
            "--kind",
            "experiment",
            "--parent",
            "intake-root",
            "--title",
            node_id,
            "--artifact-path",
            artifact,
        ]
        if manifest:
            args.extend(["--evidence-path", manifest])
        if active:
            args.append("--active")
        result = run_cli(self.root, *args)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def add_completed_review_route(self, experiment_id: str, manifest: str, review_result: str) -> str:
        review_id = "review-typed"
        review_artifact = f"research/artifacts/{review_id}.md"
        self.write_artifact(review_artifact)
        review = run_cli(
            self.root,
            "add-node",
            "--id",
            review_id,
            "--kind",
            "review",
            "--status",
            "done",
            "--parent",
            experiment_id,
            "--title",
            "Typed review",
            "--artifact-path",
            review_artifact,
            "--artifact-path",
            review_result,
            "--evidence-path",
            manifest,
        )
        self.assertEqual(review.returncode, 0, review.stdout + review.stderr)
        decision_artifact = "research/artifacts/decision-after-review.md"
        self.write_artifact(decision_artifact)
        decision = run_cli(
            self.root,
            "add-node",
            "--id",
            "decision-after-review",
            "--kind",
            "decision",
            "--parent",
            review_id,
            "--title",
            "Act on typed review",
            "--artifact-path",
            decision_artifact,
            "--active",
        )
        self.assertEqual(decision.returncode, 0, decision.stdout + decision.stderr)
        return review_id

    def test_init_uses_v2_templates_and_unicode(self) -> None:
        graph = self.graph()
        self.assertEqual(graph["schema_version"], "ds-lite.graph.v2")
        self.assertEqual(graph["revision"], 0)
        self.assertEqual(graph["nodes"]["intake-root"]["summary"], "状态图是否可靠？")
        self.assertIn("# 中文项目", (self.root / "PROJECT.md").read_text(encoding="utf-8"))
        self.assertIn("- Revision: `0`", (self.root / "RESEARCH_MAP.md").read_text(encoding="utf-8"))
        initial_status = (self.root / "STATUS.md").read_text(encoding="utf-8")
        self.assertIn("Work unit: `work-intake`", initial_status)
        self.assertIn("Claim readiness: none", initial_status)
        self.assertIn("Validated evidence: 0", initial_status)
        self.assertIn("Off-route blocked: 0", initial_status)
        self.assertTrue((self.root / "research" / "evidence").is_dir())
        self.assertTrue((self.root / "run_review.sh").is_file())
        self.assertTrue((self.root / "tools" / "ds_lite_runtime.sh").is_file())

        generated_scripts = [
            self.root / "run_research.sh",
            self.root / "run_experiment.sh",
            self.root / "run_review.sh",
            self.root / "run_analysis.sh",
            self.root / "tools" / "ds_lite_runtime.sh",
        ]
        forbidden_fragments = (
            ".codex/plugins/cache",
            ".codex\\plugins\\cache",
            "C:/Users/",
            "C:\\Users\\",
            str(REPO_ROOT),
            str(REPO_ROOT).replace("\\", "/"),
        )
        for script in generated_scripts:
            content = script.read_text(encoding="utf-8")
            self.assertTrue(content.startswith("#!/usr/bin/env bash\n"), script)
            for forbidden in forbidden_fragments:
                self.assertNotIn(forbidden, content, script)

        bash = portable_bash()
        if bash:
            environment = os.environ.copy()
            environment.update(
                {
                    "PYTHON_BIN": Path(sys.executable).as_posix(),
                    "DS_LITE_PLUGIN_ROOT": (REPO_ROOT / "plugins" / "deepscientist-lite").as_posix(),
                }
            )
            for script in generated_scripts:
                checked = subprocess.run(
                    [bash, "-n", script.as_posix()],
                    cwd=self.root,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    capture_output=True,
                    env=environment,
                )
                self.assertEqual(checked.returncode, 0, checked.stderr)
            replayed = subprocess.run(
                [bash, (self.root / "run_research.sh").as_posix(), "status", "--json"],
                cwd=self.root,
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                env=environment,
            )
            self.assertEqual(replayed.returncode, 0, replayed.stderr)
            self.assertEqual(json.loads(replayed.stdout)["active_node_id"], "intake-root")
            mission_replayed = subprocess.run(
                [bash, (self.root / "run_research.sh").as_posix(), "mission", "--format", "json"],
                cwd=self.root,
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                env=environment,
            )
            self.assertEqual(mission_replayed.returncode, 0, mission_replayed.stderr)
            self.assertEqual(json.loads(mission_replayed.stdout)["active_node_id"], "intake-root")

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

    def test_legacy_experiment_without_evidence_pack_warns_and_strict_fails(self) -> None:
        self.write_artifact("research/artifacts/experiment-legacy.md")
        added = run_cli(
            self.root,
            "add-node",
            "--id",
            "experiment-legacy",
            "--kind",
            "experiment",
            "--parent",
            "intake-root",
            "--title",
            "Legacy experiment",
            "--artifact-path",
            "research/artifacts/experiment-legacy.md",
            "--active",
        )
        self.assertEqual(added.returncode, 0, added.stderr)
        regular = run_cli(self.root, "validate")
        self.assertEqual(regular.returncode, 0, regular.stderr)
        self.assertTrue(any("no Evidence Pack manifest" in item for item in parse_output(regular)["warnings"]))
        strict = run_cli(self.root, "validate", "--strict")
        self.assertEqual(strict.returncode, 1)

    def test_active_route_strict_keeps_off_route_evidence_warning_visible(self) -> None:
        self.write_artifact("research/artifacts/experiment-a.md")
        self.write_artifact("research/artifacts/idea-b.md")
        failed_branch = run_cli(
            self.root,
            "add-node",
            "--id",
            "experiment-a",
            "--kind",
            "experiment",
            "--parent",
            "intake-root",
            "--relation",
            "branch",
            "--title",
            "Failed branch A",
            "--artifact-path",
            "research/artifacts/experiment-a.md",
        )
        self.assertEqual(failed_branch.returncode, 0, failed_branch.stderr)
        active_branch = run_cli(
            self.root,
            "add-node",
            "--id",
            "idea-b",
            "--kind",
            "idea",
            "--parent",
            "intake-root",
            "--relation",
            "branch",
            "--title",
            "Compliant branch B",
            "--artifact-path",
            "research/artifacts/idea-b.md",
            "--active",
        )
        self.assertEqual(active_branch.returncode, 0, active_branch.stderr)

        global_result = run_cli(self.root, "validate", "--strict")
        self.assertEqual(global_result.returncode, 1, global_result.stdout + global_result.stderr)
        global_payload = parse_output(global_result)
        self.assertEqual(global_payload["scope"], "all")
        self.assertIn("experiment node experiment-a has no Evidence Pack manifest", global_payload["warnings"])
        self.assertEqual(global_payload["off_route_warnings"], [])

        route_result = run_cli(self.root, "validate", "--strict", "--scope", "active-route")
        self.assertEqual(route_result.returncode, 0, route_result.stdout + route_result.stderr)
        route_payload = parse_output(route_result)
        self.assertTrue(route_payload["ok"])
        self.assertEqual(route_payload["active_route"], ["intake-root", "idea-b"])
        self.assertEqual(route_payload["warnings"], [])
        self.assertIn(
            "experiment node experiment-a has no Evidence Pack manifest",
            route_payload["off_route_warnings"],
        )
        self.assertEqual(route_payload["warning_count"], 1)

    def test_review_node_supports_block_and_analysis_route(self) -> None:
        self.write_artifact("research/artifacts/experiment-reviewed.md")
        manifest = self.write_evidence_manifest("experiment-reviewed", "reviewed-run")
        experiment = run_cli(
            self.root,
            "add-node",
            "--id",
            "experiment-reviewed",
            "--kind",
            "experiment",
            "--parent",
            "intake-root",
            "--title",
            "Reviewed experiment",
            "--artifact-path",
            "research/artifacts/experiment-reviewed.md",
            "--evidence-path",
            manifest,
            "--active",
        )
        self.assertEqual(experiment.returncode, 0, experiment.stderr)
        self.write_artifact("research/artifacts/review-reviewed.md")
        review = run_cli(
            self.root,
            "add-node",
            "--id",
            "review-reviewed",
            "--kind",
            "review",
            "--parent",
            "experiment-reviewed",
            "--title",
            "Independent review pass",
            "--artifact-path",
            "research/artifacts/review-reviewed.md",
            "--evidence-path",
            manifest,
            "--active",
        )
        self.assertEqual(review.returncode, 0, review.stderr)
        blocked = run_cli(self.root, "set-status", "--node", "review-reviewed", "--status", "blocked")
        self.assertEqual(blocked.returncode, 0, blocked.stderr)
        resumed = run_cli(self.root, "set-status", "--node", "review-reviewed", "--status", "active")
        self.assertEqual(resumed.returncode, 0, resumed.stderr)
        self.write_artifact("research/artifacts/analysis-reviewed.md")
        analysis = run_cli(
            self.root,
            "add-node",
            "--id",
            "analysis-reviewed",
            "--kind",
            "analysis",
            "--parent",
            "review-reviewed",
            "--title",
            "Reviewed analysis",
            "--artifact-path",
            "research/artifacts/analysis-reviewed.md",
            "--active",
        )
        self.assertEqual(analysis.returncode, 0, analysis.stderr)
        strict = run_cli(self.root, "validate", "--strict")
        self.assertEqual(strict.returncode, 0, strict.stdout + strict.stderr)
        trace = parse_output(run_cli(self.root, "trace", "--node", "analysis-reviewed"))
        self.assertEqual(
            [item["id"] for item in trace["route"]],
            ["intake-root", "experiment-reviewed", "review-reviewed", "analysis-reviewed"],
        )

    def test_status_update_clamps_a_regressed_wall_clock(self) -> None:
        added = run_cli(
            self.root,
            "add-node",
            "--id",
            "future-clock-node",
            "--kind",
            "scout",
            "--parent",
            "intake-root",
            "--title",
            "Future clock node",
        )
        self.assertEqual(added.returncode, 0, added.stderr)
        graph_path = self.root / "research" / "state" / "graph.json"
        graph = json.loads(graph_path.read_text(encoding="utf-8"))
        future = "2999-01-01T00:00:00Z"
        graph["nodes"]["future-clock-node"]["created_at"] = future
        graph["nodes"]["future-clock-node"]["updated_at"] = future
        graph_path.write_text(json.dumps(graph, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

        updated = run_cli(self.root, "set-status", "--node", "future-clock-node", "--status", "done")
        self.assertEqual(updated.returncode, 0, updated.stderr)
        graph = json.loads(graph_path.read_text(encoding="utf-8"))
        self.assertEqual(graph["nodes"]["future-clock-node"]["updated_at"], future)
        strict = run_cli(self.root, "validate", "--strict")
        self.assertEqual(strict.returncode, 0, strict.stdout + strict.stderr)

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

    def test_t01_new_project_has_planning_evidence_state(self) -> None:
        self.assertTrue((self.root / "research" / "work-unit.json").is_file())
        artifact = "research/artifacts/ordinary-output.log"
        self.write_artifact(artifact)
        ordinary = run_cli(
            self.root,
            "add-node",
            "--id",
            "experiment-ordinary-path",
            "--kind",
            "experiment",
            "--parent",
            "intake-root",
            "--title",
            "Ordinary output is not typed evidence",
            "--artifact-path",
            artifact,
            "--evidence-path",
            artifact,
            "--active",
        )
        self.assertEqual(ordinary.returncode, 0, ordinary.stdout + ordinary.stderr)
        mission = parse_output(run_cli(self.root, "mission"))
        self.assertIn("work_unit", mission)
        self.assertEqual(mission["work_unit"]["work_unit_id"], "work-intake")
        self.assertEqual(mission["evidence_strength"], "planning")
        self.assertEqual(mission["claim_readiness"], "none")
        self.assertEqual(mission["evidence_detail"]["validated_evidence_count"], 0)

    def test_review_result_template_renders_to_a_valid_protocol_object(self) -> None:
        rendered = Template(REVIEW_RESULT_TEMPLATE.read_text(encoding="utf-8")).substitute(
            review_id_json=json.dumps("review-template"),
            work_unit_id_json=json.dumps("work-main"),
            profile_id_json=json.dumps("experiment-run"),
            review_node_id_json=json.dumps("review-template"),
            reviewed_node_id_json=json.dumps("experiment-template"),
            reviewed_evidence_refs_json=json.dumps(
                ["research/evidence/template-run/manifest.json"]
            ),
            evidence_validator_json=json.dumps("ds-lite.evidence.v1"),
            evidence_digest_json=json.dumps("0" * 64),
            verdict_json=json.dumps("pass"),
            claim_assessment_json=json.dumps("supportable"),
            channels_json=json.dumps({"integrity": "pass"}),
            limitations_json=json.dumps([]),
            review_artifact_ref_json=json.dumps("research/artifacts/review-template.md"),
            completed_at_json=json.dumps("2026-07-16T00:00:00Z"),
        )
        validated = ds_lite_protocol.validate_review_result(json.loads(rendered))
        self.assertEqual(validated["schema_version"], "ds-lite.review-result.v1")

    def test_t02_claim_requirement_without_validator_or_evidence_needs_evidence(self) -> None:
        self.write_work_unit(
            profile_id="unknown-claim-profile",
            evidence_requirements=[{"kind": "claim-record", "validator": "unknown.validator.v1"}],
        )
        self.add_experiment_node("experiment-no-validator")
        mission = parse_output(run_cli(self.root, "mission"))
        self.assertEqual(mission["evidence_strength"], "needs-evidence")
        self.assertEqual(mission["claim_readiness"], "blocked")
        self.assertTrue(any("validator" in item for item in mission["evidence_detail"]["blocking_reasons"]))
        markdown = run_cli(self.root, "mission", "--format", "markdown")
        self.assertEqual(markdown.returncode, 0, markdown.stderr)
        self.assertIn("Evidence blockers", markdown.stdout)
        self.assertIn("profile validator missing", markdown.stdout)
        strict = run_cli(self.root, "validate", "--strict", "--scope", "active-route")
        self.assertEqual(strict.returncode, 1)

    def test_t03_damaged_typed_evidence_does_not_upgrade_strength(self) -> None:
        manifest = self.write_evidence_manifest("experiment-damaged", "damaged")
        self.write_work_unit(
            profile_id="experiment-run",
            evidence_requirements=[{"kind": "experiment-pack", "validator": "ds-lite.evidence.v1"}],
            evidence_refs=[manifest],
        )
        self.add_experiment_node("experiment-damaged", manifest)
        path = self.root / manifest
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["schema_version"] = "wrong.evidence.v1"
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        mission = parse_output(run_cli(self.root, "mission"))
        self.assertEqual(mission["evidence_strength"], "needs-evidence")
        self.assertEqual(mission["claim_readiness"], "blocked")
        self.assertTrue(any("damaged" in item or "schema" in item for item in mission["evidence_detail"]["blocking_reasons"]))

    def test_profile_validator_pending_or_failed_does_not_upgrade_strength(self) -> None:
        manifest = self.write_evidence_manifest("experiment-validator-state", "validator-state-run")
        self.write_work_unit(
            profile_id="experiment-run",
            evidence_requirements=[{"kind": "experiment-pack", "validator": "ds-lite.evidence.v1"}],
            evidence_refs=[manifest],
        )
        self.add_experiment_node("experiment-validator-state", manifest)
        path = self.root / manifest
        valid = json.loads(path.read_text(encoding="utf-8"))
        for status in ("pending", "fail"):
            with self.subTest(status=status):
                payload = json.loads(json.dumps(valid))
                payload["verification"]["status"] = status
                path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                mission = parse_output(run_cli(self.root, "mission"))
                self.assertEqual(mission["evidence_strength"], "needs-evidence")
                self.assertEqual(mission["claim_readiness"], "blocked")
                self.assertTrue(
                    any("has not recorded pass" in item for item in mission["evidence_detail"]["blocking_reasons"])
                )

    def test_t04_complete_failed_run_is_evidence_but_not_supportable(self) -> None:
        manifest = self.write_evidence_manifest(
            "experiment-negative",
            "negative-run",
            metrics=[{"name": "failure_observation", "direction": "observe"}],
            exit_code=7,
        )
        self.write_work_unit(
            profile_id="experiment-run",
            evidence_requirements=[{"kind": "experiment-pack", "validator": "ds-lite.evidence.v1"}],
            evidence_refs=[manifest],
        )
        self.add_experiment_node("experiment-negative", manifest)
        mission = parse_output(run_cli(self.root, "mission"))
        self.assertEqual(mission["evidence_strength"], "has-evidence")
        self.assertIn("claim_readiness", mission)
        self.assertEqual(mission["claim_readiness"], "inconclusive")
        self.assertEqual(mission["evidence_detail"]["negative_evidence_count"], 1)
        self.assertNotEqual(mission["claim_readiness"], "supportable")

    def test_t05_active_markdown_only_review_is_not_reviewed(self) -> None:
        manifest = self.write_evidence_manifest("experiment-for-review", "review-input-run")
        self.write_work_unit(
            profile_id="experiment-run",
            evidence_requirements=[{"kind": "experiment-pack", "validator": "ds-lite.evidence.v1"}],
            evidence_refs=[manifest],
        )
        self.add_experiment_node("experiment-for-review", manifest)
        review_artifact = "research/artifacts/review-markdown-only.md"
        self.write_artifact(review_artifact)
        review = run_cli(
            self.root,
            "add-node",
            "--id",
            "review-markdown-only",
            "--kind",
            "review",
            "--parent",
            "experiment-for-review",
            "--title",
            "Markdown-only review",
            "--artifact-path",
            review_artifact,
            "--evidence-path",
            manifest,
            "--active",
        )
        self.assertEqual(review.returncode, 0, review.stdout + review.stderr)
        mission = parse_output(run_cli(self.root, "mission"))
        self.assertEqual(mission["evidence_strength"], "has-evidence")
        self.assertEqual(mission["evidence_detail"]["review_result_count"], 0)
        self.assertNotEqual(mission["evidence_strength"], "reviewed")
        (self.root / review_artifact).write_text("", encoding="utf-8")
        empty_mission = parse_output(run_cli(self.root, "mission"))
        self.assertEqual(empty_mission["evidence_strength"], "has-evidence")
        decision_artifact = "research/artifacts/decision-after-markdown-review.md"
        self.write_artifact(decision_artifact)
        decision = run_cli(
            self.root,
            "add-node",
            "--id",
            "decision-after-markdown-review",
            "--kind",
            "decision",
            "--parent",
            "review-markdown-only",
            "--title",
            "Do not accept prose-only review",
            "--artifact-path",
            decision_artifact,
            "--active",
        )
        self.assertEqual(decision.returncode, 0, decision.stdout + decision.stderr)
        done_mission = parse_output(run_cli(self.root, "mission"))
        self.assertEqual(done_mission["evidence_strength"], "has-evidence")
        markdown = run_cli(self.root, "mission", "--format", "markdown")
        self.assertEqual(markdown.returncode, 0, markdown.stderr)
        self.assertIn("Compatibility warnings", markdown.stdout)
        self.assertIn("ds-lite.review-result.v1", markdown.stdout)

    def test_t06_typed_review_verdict_and_claim_assessment_are_orthogonal(self) -> None:
        manifest = self.write_evidence_manifest("experiment-typed", "typed-review-run")
        self.write_work_unit(
            profile_id="experiment-run",
            evidence_requirements=[{"kind": "experiment-pack", "validator": "ds-lite.evidence.v1"}],
            evidence_refs=[manifest],
        )
        self.add_experiment_node("experiment-typed", manifest)
        review_result = self.write_review_result(
            review_node_id="review-typed",
            reviewed_node_id="experiment-typed",
            evidence_refs=[manifest],
            verdict="pass",
            claim_assessment="supportable",
            extensions={"profile_note": "forward-compatible"},
        )
        self.add_completed_review_route("experiment-typed", manifest, review_result)

        mission = parse_output(run_cli(self.root, "mission"))
        self.assertEqual(mission["evidence_strength"], "reviewed")
        self.assertIn("claim_readiness", mission)
        self.assertEqual(mission["claim_readiness"], "supportable")
        self.assertEqual(mission["evidence_detail"]["review_result_count"], 1)

        cases = (
            ("pass", "refuted", "refuted", False),
            ("pass", "inconclusive", "inconclusive", False),
            ("fail", "refuted", "blocked", False),
            ("needs-human", "inconclusive", "blocked", True),
        )
        for verdict, assessment, readiness, waiting in cases:
            with self.subTest(verdict=verdict, assessment=assessment):
                self.write_review_result(
                    review_node_id="review-typed",
                    reviewed_node_id="experiment-typed",
                    evidence_refs=[manifest],
                    verdict=verdict,
                    claim_assessment=assessment,
                )
                mission = parse_output(run_cli(self.root, "mission"))
                self.assertEqual(mission["evidence_strength"], "reviewed")
                self.assertEqual(mission["claim_readiness"], readiness)
                self.assertEqual(mission["waiting_for_user"], waiting)

    def test_work_unit_schema_rejects_unsafe_or_ambiguous_fixtures(self) -> None:
        valid = self.write_work_unit(extensions={"future": {"mode": "accepted"}})
        mission = parse_output(run_cli(self.root, "mission"))
        self.assertFalse(any("work unit" in item for item in mission["validation"]["errors"]))

        cases = []
        missing = dict(valid)
        missing.pop("goal")
        cases.append((missing, "missing fields"))
        cases.append(({**valid, "execution_mode": "daemon"}, "execution_mode"))
        cases.append(({**valid, "prerequisites": ["../escape"]}, "normalized"))
        cases.append(({**valid, "extensions": {"api_token": "secret"}}, "sensitive"))
        cases.append(
            (
                {
                    **valid,
                    "subjects": [
                        {"kind": "artifact", "id": "same", "query_ref": "PROJECT.md"},
                        {"kind": "artifact", "id": "same", "query_ref": "STATUS.md"},
                    ],
                },
                "duplicate subject id",
            )
        )
        cases.append(({**valid, "future_top_level": "no"}, "unsupported fields"))
        for payload, expected in cases:
            with self.subTest(expected=expected):
                (self.root / "research" / "work-unit.json").write_text(
                    json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
                )
                mission = parse_output(run_cli(self.root, "mission"))
                self.assertTrue(any(expected in item for item in mission["validation"]["errors"]), mission)

    def test_review_result_schema_rejects_unsafe_or_conflicting_fixtures(self) -> None:
        manifest = self.write_evidence_manifest("experiment-schema", "review-schema-run")
        self.write_work_unit(
            profile_id="experiment-run",
            evidence_requirements=[{"kind": "experiment-pack", "validator": "ds-lite.evidence.v1"}],
            evidence_refs=[manifest],
        )
        self.add_experiment_node("experiment-schema", manifest)
        review_path = self.write_review_result(
            review_node_id="review-typed",
            reviewed_node_id="experiment-schema",
            evidence_refs=[manifest],
            extensions={"future": "accepted"},
        )
        self.add_completed_review_route("experiment-schema", manifest, review_path)
        path = self.root / review_path
        valid = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(parse_output(run_cli(self.root, "mission"))["evidence_strength"], "reviewed")

        missing = dict(valid)
        missing.pop("verdict")
        cases = [
            (missing, "missing fields"),
            ({**valid, "verdict": "approved"}, "verdict"),
            ({**valid, "review_artifact_ref": "../escape"}, "normalized"),
            ({**valid, "extensions": {"chain_of_thought": "hidden"}}, "sensitive"),
            (
                {
                    **valid,
                    "review_id": "experiment-schema",
                    "review_node_id": "experiment-schema",
                },
                "must differ",
            ),
            ({**valid, "evidence_validator": "other.validator.v1"}, "validator does not match"),
            ({**valid, "future_top_level": "no"}, "unsupported fields"),
        ]
        for payload, expected in cases:
            with self.subTest(expected=expected):
                path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                mission = parse_output(run_cli(self.root, "mission"))
                self.assertNotEqual(mission["evidence_strength"], "reviewed")
                self.assertTrue(
                    any(expected in item for item in mission["evidence_detail"]["blocking_reasons"]), mission
                )

    def test_mission_board_reports_visible_route_and_renders_status(self) -> None:
        self.write_artifact("research/artifacts/idea-fusion-v2.md")
        self.write_artifact("research/artifacts/experiment-fusion-v2.md")
        self.write_artifact("research/artifacts/idea-fusion-v3.md")
        self.write_artifact("research/artifacts/decision-adaptive-v4.md")
        manifest = self.write_evidence_manifest(
            "experiment-fusion-v2",
            run_id="fusion-v2-run",
            metrics=[
                {"name": "simple_regret_final", "direction": "min", "threshold": 0.12},
                {"name": "normalized_auc", "direction": "max", "threshold": 0.82},
            ],
            budget={"value": 50, "unit": "trials"},
        )
        self.write_work_unit(
            profile_id="experiment-run",
            evidence_requirements=[{"kind": "experiment-pack", "validator": "ds-lite.evidence.v1"}],
            evidence_refs=[manifest],
        )

        idea = run_cli(
            self.root,
            "add-node",
            "--id",
            "idea-fusion-v2",
            "--kind",
            "idea",
            "--parent",
            "intake-root",
            "--relation",
            "branch",
            "--title",
            "Fusion v2 policy",
            "--summary",
            "v2 has strong AUC but final convergence is unstable.",
            "--artifact-path",
            "research/artifacts/idea-fusion-v2.md",
            "--active",
        )
        self.assertEqual(idea.returncode, 0, idea.stderr)
        experiment = run_cli(
            self.root,
            "add-node",
            "--id",
            "experiment-fusion-v2",
            "--kind",
            "experiment",
            "--parent",
            "idea-fusion-v2",
            "--relation",
            "next",
            "--title",
            "Fusion v2 smoke",
            "--summary",
            "Smoke run captured the AUC/final-regret tradeoff.",
            "--artifact-path",
            "research/artifacts/experiment-fusion-v2.md",
            "--evidence-path",
            "research/evidence/fusion-v2-run/manifest.json",
            "--active",
        )
        self.assertEqual(experiment.returncode, 0, experiment.stderr)
        v3 = run_cli(
            self.root,
            "add-node",
            "--id",
            "idea-fusion-v3",
            "--kind",
            "idea",
            "--parent",
            "experiment-fusion-v2",
            "--relation",
            "branch",
            "--title",
            "Fusion v3 final-regret route",
            "--summary",
            "v3 improves final regret but hurts aggregate AUC.",
            "--artifact-path",
            "research/artifacts/idea-fusion-v3.md",
        )
        self.assertEqual(v3.returncode, 0, v3.stderr)
        decision = run_cli(
            self.root,
            "add-node",
            "--id",
            "decision-adaptive-v4",
            "--kind",
            "decision",
            "--parent",
            "experiment-fusion-v2",
            "--relation",
            "branch",
            "--title",
            "Branch adaptive v4",
            "--summary",
            "Branch from v2 because v3 improved final regret but hurt AUC.",
            "--artifact-path",
            "research/artifacts/decision-adaptive-v4.md",
        )
        self.assertEqual(decision.returncode, 0, decision.stderr)
        supersedes = run_cli(
            self.root,
            "add-edge",
            "--from",
            "decision-adaptive-v4",
            "--to",
            "idea-fusion-v3",
            "--relation",
            "supersedes",
            "--reason",
            "Adaptive v4 should branch from v2 instead of inheriting v3's AUC regression.",
            "--artifact-path",
            "research/artifacts/decision-adaptive-v4.md",
        )
        self.assertEqual(supersedes.returncode, 0, supersedes.stderr)
        rollback = run_cli(
            self.root,
            "add-edge",
            "--from",
            "decision-adaptive-v4",
            "--to",
            "idea-fusion-v2",
            "--relation",
            "rollback",
            "--reason",
            "Return to v2 if adaptive v4 smoke fails.",
            "--artifact-path",
            "research/artifacts/decision-adaptive-v4.md",
        )
        self.assertEqual(rollback.returncode, 0, rollback.stderr)

        mission = parse_output(run_cli(self.root, "mission"))
        self.assertEqual(mission["active_node_id"], "experiment-fusion-v2")
        self.assertEqual(mission["stage"], "experiment")
        self.assertIn("experiment-fusion-v2", mission["active_route"])
        self.assertEqual(mission["evidence_strength"], "has-evidence")
        self.assertIn("decision-adaptive-v4", [item["id"] for item in mission["candidate_queue"]])
        self.assertIn("idea-fusion-v2", [item["to"] for item in mission["rollback_targets"]])
        self.assertIn("idea-fusion-v3", [item["to"] for item in mission["supersedes"]])
        metric_surfaces = mission["metric_surfaces"]
        self.assertIn("normalized_auc", [item["name"] for item in metric_surfaces])
        self.assertIn("simple_regret_final", [item["name"] for item in metric_surfaces])
        self.assertIn("aggregate", [item["surface"] for item in metric_surfaces])
        self.assertIn("final", [item["surface"] for item in metric_surfaces])
        self.assertIn("max", [item["direction"] for item in metric_surfaces])
        self.assertIn("min", [item["direction"] for item in metric_surfaces])
        self.assertIn("artifact != progress", mission["readiness_rules"])
        self.assertFalse(mission["waiting_for_user"])

        markdown = run_cli(self.root, "mission", "--format", "markdown")
        self.assertEqual(markdown.returncode, 0, markdown.stderr)
        self.assertIn("## Mission Board", markdown.stdout)
        self.assertIn("Work unit: `work-main`", markdown.stdout)
        self.assertIn("Claim readiness: inconclusive", markdown.stdout)
        self.assertIn("Validated evidence: 1", markdown.stdout)
        self.assertIn(manifest, markdown.stdout)
        self.assertIn("Next Action", markdown.stdout)
        self.assertIn("normalized_auc", markdown.stdout)

        rendered = parse_output(run_cli(self.root, "render-status"))
        self.assertTrue(rendered["ok"])
        status = (self.root / "STATUS.md").read_text(encoding="utf-8")
        self.assertIn("## Mission Board", status)
        self.assertIn("Fusion v2 smoke", status)
        self.assertIn("artifact != progress", status)
        self.assertIn("decision-adaptive-v4", status)
        self.assertIn("simple_regret_final", status)
        self.assertIn("normalized_auc", status)
        self.assertIn("Claim readiness: inconclusive", status)

    def test_mission_projects_latest_iteration_and_merged_hypothesis_pool(self) -> None:
        evidence_ref = "research/artifacts/hypothesis-check.md"
        self.write_artifact(evidence_ref, "# Bounded check\n\nRoute A failed its discriminating condition.\n")
        route_a_artifact = "research/artifacts/idea-route-a.md"
        route_b_artifact = "research/artifacts/idea-route-b.md"
        factor_ref = "research/artifacts/factor-card-route-b.json"
        self.write_artifact(route_a_artifact, "# Route A\n")
        self.write_artifact(route_b_artifact, "# Route B\n")
        factor = {
            "schema_version": "ds-lite.factor-card.v1",
            "factor_card_id": "factor-card-route-b",
            "work_unit_id": "work-intake",
            "profile_id": "core-planning",
            "subject_ref": route_b_artifact,
            "status": "draft",
            "factors": [
                {
                    "name": name,
                    "score": None,
                    "confidence": "unknown",
                    "evidence_refs": [],
                    "summary": f"{name} is not measured.",
                    "uncertainty": ["One bounded check remains."],
                    "extensions": {},
                }
                for name in (
                    "novelty",
                    "feasibility",
                    "evidence_strength",
                    "cost",
                    "risk",
                    "alignment",
                )
            ],
            "decision": "explore",
            "minimal_test": {
                "question": "Does Route B survive one bounded probe?",
                "method": "Run one single-axis comparison.",
                "expected_evidence": ["A reproducible positive or negative result."],
                "resource_limits": [{"dimension": "actions", "unit": "count", "value": 1}],
                "stop_condition": "Stop after one probe.",
                "extensions": {},
            },
            "created_at": utc_now(),
            "updated_at": utc_now(),
            "extensions": {},
        }
        (self.root / factor_ref).write_text(
            json.dumps(factor, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        route_a = run_cli(
            self.root,
            "add-node",
            "--id",
            "idea-route-a",
            "--kind",
            "idea",
            "--parent",
            "intake-root",
            "--relation",
            "branch",
            "--title",
            "Route A",
            "--summary",
            "Candidate mechanism A.",
            "--artifact-path",
            route_a_artifact,
            "--active",
        )
        self.assertEqual(route_a.returncode, 0, route_a.stdout + route_a.stderr)
        route_b = run_cli(
            self.root,
            "add-node",
            "--id",
            "idea-route-b",
            "--kind",
            "idea",
            "--parent",
            "intake-root",
            "--relation",
            "branch",
            "--title",
            "Route B",
            "--summary",
            "Candidate mechanism B.",
            "--artifact-path",
            route_b_artifact,
            "--artifact-path",
            factor_ref,
        )
        self.assertEqual(route_b.returncode, 0, route_b.stdout + route_b.stderr)
        revision = self.graph()["revision"]
        running = ds_lite_iteration.initialize_iteration(
            self.root,
            iteration_id="iteration-reflection-001",
            selected_skill="ds-lite-iterate",
            action={
                "kind": "idea",
                "summary": "Reassess the current hypothesis pool.",
                "prediction": "Route A will weaken under the bounded check.",
                "falsification_condition": "Route A satisfies the declared condition.",
                "resource_limits": [{"dimension": "actions", "unit": "count", "value": 1}],
                "stop_condition": "Stop after one check and reflection.",
                "extensions": {},
            },
            input_refs=["PROJECT.md", route_a_artifact, factor_ref],
            expected_revision=revision,
        )
        updates = []
        for hypothesis_id, status in (
            ("idea-route-a", "refuted"),
            ("hypothesis-supported", "supported"),
            ("hypothesis-weakened", "weakened"),
            ("hypothesis-inconclusive", "inconclusive"),
            ("hypothesis-parked", "parked"),
        ):
            updates.append(
                {
                    "hypothesis_id": hypothesis_id,
                    "status": status,
                    "evidence_refs": [evidence_ref] if status in {"refuted", "supported", "weakened"} else [],
                    "summary": f"Reflection recorded {status} without changing typed evidence strength.",
                    "extensions": {},
                }
            )
        result = {
            "status": "completed",
            "after_revision": revision,
            "output_refs": [evidence_ref],
            "graph_changes": [
                {
                    "kind": "none",
                    "subject_id": "idea-route-a",
                    "summary": "Reflection changed no Graph authority.",
                    "extensions": {},
                }
            ],
            "validations": [
                {
                    "command": "python plugins/deepscientist-lite/scripts/ds_lite_state.py mission --root .",
                    "status": "pass",
                    "summary": "Mission projection remained valid.",
                    "extensions": {},
                }
            ],
            "stop_reason": "action-completed",
            "reflection": {
                "observed_outcomes": ["Route A failed the declared condition."],
                "hypothesis_updates": updates,
                "expectation_gap": "The negative result was stronger than expected.",
                "negative_results": [
                    {
                        "summary": "Route A failed the bounded check.",
                        "evidence_refs": [evidence_ref],
                        "extensions": {},
                    }
                ],
                "responsibility": {
                    "authorization_basis": "Local bounded check only.",
                    "boundaries_respected": ["No external execution."],
                    "unresolved_obligations": ["Route B remains untested."],
                    "extensions": {},
                },
                "learned_boundaries": ["Candidate selection is not claim evidence."],
                "next_candidates": [
                    {
                        "hypothesis_id": "idea-route-b",
                        "title": "Route B",
                        "status": "untested",
                        "minimal_test": "Run the Factor Card minimal test.",
                        "extensions": {},
                    }
                ],
                "minimal_discriminating_test": "Run one single-axis Route B probe.",
                "extensions": {},
            },
            "user_report": {
                "summary": "Refuted Route A and preserved Route B as untested.",
                "files_changed": [evidence_ref],
                "validation_summary": "Mission projection passed.",
                "failure_layer": "none",
                "unverified": ["Route B mechanism and novelty remain untested."],
                "hypothesis_changes": ["idea-route-a: untested -> refuted"],
                "next_action": "Run one bounded Route B probe.",
                "decision_needed": "none",
                "extensions": {},
            },
            "completed_at": utc_now(),
            "extensions": {},
        }
        ds_lite_iteration.finalize_iteration(
            self.root, running["extensions"]["iteration_ref"], result
        )

        mission = parse_output(run_cli(self.root, "mission"))
        self.assertEqual(mission["latest_iteration"]["iteration_id"], "iteration-reflection-001")
        self.assertEqual(mission["latest_iteration"]["status"], "completed")
        self.assertIn("stronger than expected", mission["latest_iteration"]["reflection"]["expectation_gap"])
        statuses = {item["hypothesis_id"]: item["status"] for item in mission["hypothesis_pool"]}
        self.assertEqual(statuses["idea-route-a"], "refuted")
        self.assertEqual(statuses["idea-route-b"], "untested")
        self.assertEqual(statuses["hypothesis-supported"], "supported")
        self.assertEqual(statuses["hypothesis-weakened"], "weakened")
        self.assertEqual(statuses["hypothesis-inconclusive"], "inconclusive")
        self.assertEqual(statuses["hypothesis-parked"], "parked")
        route_a_record = next(item for item in mission["hypothesis_pool"] if item["hypothesis_id"] == "idea-route-a")
        self.assertEqual(route_a_record["negative_result_count"], 1)
        route_b_record = next(item for item in mission["hypothesis_pool"] if item["hypothesis_id"] == "idea-route-b")
        self.assertIn(factor_ref, route_b_record["source_refs"])
        self.assertEqual(mission["evidence_strength"], "planning")

        markdown = run_cli(self.root, "mission", "--format", "markdown")
        self.assertEqual(markdown.returncode, 0, markdown.stderr)
        self.assertIn("## Latest Iteration", markdown.stdout)
        self.assertIn("## Hypothesis Pool", markdown.stdout)
        self.assertIn("idea-route-a", markdown.stdout)
        self.assertIn("refuted", markdown.stdout)

    def test_t07_off_route_blocked_review_does_not_force_waiting_for_user(self) -> None:
        self.write_artifact("research/artifacts/experiment-needs-review.md")
        self.write_artifact("research/artifacts/review-needs-human.md")
        manifest = self.write_evidence_manifest("experiment-needs-review", run_id="needs-review-run")
        self.write_work_unit(
            profile_id="experiment-run",
            evidence_requirements=[{"kind": "experiment-pack", "validator": "ds-lite.evidence.v1"}],
            evidence_refs=[manifest],
        )
        experiment = run_cli(
            self.root,
            "add-node",
            "--id",
            "experiment-needs-review",
            "--kind",
            "experiment",
            "--parent",
            "intake-root",
            "--title",
            "Experiment awaiting human review",
            "--artifact-path",
            "research/artifacts/experiment-needs-review.md",
            "--evidence-path",
            manifest,
            "--active",
        )
        self.assertEqual(experiment.returncode, 0, experiment.stderr)
        review = run_cli(
            self.root,
            "add-node",
            "--id",
            "review-needs-human",
            "--kind",
            "review",
            "--status",
            "blocked",
            "--parent",
            "experiment-needs-review",
            "--relation",
            "next",
            "--title",
            "Human review required",
            "--summary",
            "Metric direction correction requires user confirmation.",
            "--artifact-path",
            "research/artifacts/review-needs-human.md",
            "--evidence-path",
            manifest,
        )
        self.assertEqual(review.returncode, 0, review.stderr)
        block_edge = run_cli(
            self.root,
            "add-edge",
            "--from",
            "review-needs-human",
            "--to",
            "experiment-needs-review",
            "--relation",
            "blocks",
            "--reason",
            "Protocol-breaking metric correction must be reviewed before analysis.",
            "--artifact-path",
            "research/artifacts/review-needs-human.md",
        )
        self.assertEqual(block_edge.returncode, 0, block_edge.stderr)

        mission = parse_output(run_cli(self.root, "mission"))
        self.assertFalse(mission["waiting_for_user"])
        self.assertEqual(mission["waiting_detail"]["active_route_blocked_count"], 0)
        self.assertEqual(mission["waiting_detail"]["off_route_blocked_count"], 1)
        self.assertIn("review-needs-human", [item["id"] for item in mission["blocked_nodes"]])
        self.assertIn("experiment-needs-review", [item["to"] for item in mission["blockers"]])
        self.assertIn("Run ds-lite-review", mission["next_action"])
        markdown = run_cli(self.root, "mission", "--format", "markdown")
        self.assertEqual(markdown.returncode, 0, markdown.stderr)
        self.assertIn("Off-route blocked: 1", markdown.stdout)
        self.assertIn("Waiting for user: no", markdown.stdout)

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
