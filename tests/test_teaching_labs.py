from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
LAB_RUNNER = REPO_ROOT / "teaching" / "lab_runner.py"
STATE_SCRIPT = REPO_ROOT / "plugins" / "deepscientist-lite" / "scripts" / "ds_lite_state.py"


def run_lab(output: Path, lab: str, mode: str = "student", case: str = "clean") -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return subprocess.run(
        [
            sys.executable,
            str(LAB_RUNNER),
            "--lab",
            lab,
            "--mode",
            mode,
            "--case",
            case,
            "--output",
            str(output),
        ],
        cwd=REPO_ROOT,
        text=True,
        encoding="utf-8",
        capture_output=True,
        env=env,
    )


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


class TeachingLabTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="ds-lite-teaching-中文-"))

    def test_quickstart_student_stops_before_reference_answer(self) -> None:
        output = self.root / "quick start"
        result = run_lab(output, "quickstart")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse((output / "REFERENCE_ANSWER.md").exists())
        graph = read_json(output / "project" / "research" / "state" / "graph.json")
        self.assertEqual(graph["active_node_id"], "idea-file-handoff")
        self.assertNotIn("review", {node["kind"] for node in graph["nodes"].values()})

    def test_existing_output_is_never_overwritten(self) -> None:
        output = self.root / "keep me"
        output.mkdir()
        marker = output / "student.txt"
        marker.write_text("keep\n", encoding="utf-8")
        result = run_lab(output, "quickstart")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(marker.read_text(encoding="utf-8"), "keep\n")

    def test_evidence_cases_separate_integrity_and_threshold_failures(self) -> None:
        expectations = {
            "clean": (0, "pass", "pass"),
            "tampered": (1, "fail", "fail"),
            "threshold-miss": (1, "warning", "fail"),
        }
        for case, expected in expectations.items():
            with self.subTest(case=case):
                output = self.root / f"evidence {case}"
                result = run_lab(output, "evidence", case=case)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                summary = read_json(output / "lab-result.json")
                self.assertEqual(
                    (
                        summary["verification_exit_code"],
                        summary["verification_status"],
                        summary["expected_review_decision"],
                    ),
                    expected,
                )
                graph = read_json(output / "project" / "research" / "state" / "graph.json")
                self.assertNotIn("review", {node["kind"] for node in graph["nodes"].values()})

    def test_reference_clean_adds_passing_review_and_analysis(self) -> None:
        output = self.root / "reference clean"
        result = run_lab(output, "evidence", mode="reference")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue((output / "REFERENCE_ANSWER.md").exists())
        graph = read_json(output / "project" / "research" / "state" / "graph.json")
        self.assertEqual(graph["active_node_id"], "analysis-evidence-demo")
        env = os.environ.copy()
        env["PYTHONUTF8"] = "1"
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        validate = subprocess.run(
            [sys.executable, str(STATE_SCRIPT), "validate", "--root", str(output / "project"), "--strict"],
            cwd=REPO_ROOT,
            text=True,
            encoding="utf-8",
            errors="backslashreplace",
            capture_output=True,
            env=env,
        )
        self.assertEqual(validate.returncode, 0, validate.stdout + validate.stderr)

    def test_branch_reference_blocks_degradation_and_policy_violation(self) -> None:
        output = self.root / "branches"
        result = run_lab(output, "branches", mode="reference")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        summary = read_json(output / "lab-result.json")
        self.assertEqual(summary["expected_selection"], "B")
        self.assertEqual(summary["branches"]["a"]["verify_exit_code"], 1)
        self.assertEqual(summary["branches"]["c"]["verify_exit_code"], 0)
        graph = read_json(output / "project" / "research" / "state" / "graph.json")
        self.assertEqual(graph["nodes"]["review-branch-a"]["status"], "blocked")
        self.assertEqual(graph["nodes"]["review-branch-c"]["status"], "blocked")
        self.assertEqual(graph["active_node_id"], "analysis-branch-selection")

    def test_route_progression_ignores_supports_shortcut(self) -> None:
        output = self.root / "route"
        result = run_lab(output, "route")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        summary = read_json(output / "lab-result.json")
        progression = [node["id"] for node in summary["progression_route"]["route"]]
        all_edges = [node["id"] for node in summary["all_edges_route"]["route"]]
        self.assertEqual(progression, ["intake-root", "scout-route", "idea-route", "decision-route"])
        self.assertEqual(all_edges, ["intake-root", "decision-route"])
        status = (output / "project" / "STATUS.md").read_text(encoding="utf-8")
        self.assertIn("Active node: `decision-route`", status)
        self.assertIn("Stage: decision", status)
        self.assertIn("Revision: 5", status)

    def test_paths_use_unicode_relative_and_external_aliases(self) -> None:
        output = self.root / "paths 空格"
        result = run_lab(output, "paths")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        summary = read_json(output / "lab-result.json")
        self.assertEqual(summary["absolute_path_exit_code"], 1)
        self.assertFalse(summary["graph_contains_machine_root"])
        graph_text = (output / "project" / "research" / "state" / "graph.json").read_text(encoding="utf-8")
        self.assertIn("inputs/中文 数据.txt", graph_text)
        self.assertIn("external://dataset/观测 数据.csv", graph_text)
        self.assertNotIn(str(output.resolve()), graph_text)

    def test_revision_conflict_returns_four_then_retries(self) -> None:
        output = self.root / "revision"
        result = run_lab(output, "revision")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        summary = read_json(output / "lab-result.json")
        self.assertEqual(summary["stale_write_exit_code"], 4)
        self.assertEqual(summary["reloaded_revision"], summary["initial_revision"] + 1)
        self.assertEqual(summary["final_revision"], summary["reloaded_revision"] + 1)
        graph = read_json(output / "project" / "research" / "state" / "graph.json")
        self.assertIn("scout-session-a", graph["nodes"])
        self.assertIn("scout-session-b", graph["nodes"])


if __name__ == "__main__":
    unittest.main()
