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

    def assert_state_handoff(self, output: Path) -> dict:
        graph = read_json(output / "project" / "research" / "state" / "graph.json")
        result = read_json(output / "lab-result.json")
        status = (output / "project" / "STATUS.md").read_text(encoding="utf-8")
        handoff = result["state_handoff"]
        self.assertEqual(result["status_active_node"], graph["active_node_id"])
        self.assertEqual(result["status_revision"], graph["revision"])
        self.assertEqual(handoff["schema_version"], "ds-lite.teaching-handoff.v1")
        self.assertEqual(handoff["active_node_id"], graph["active_node_id"])
        self.assertEqual(handoff["revision"], graph["revision"])
        self.assertEqual(handoff["active_route"][-1], graph["active_node_id"])
        self.assertIn(f"Active node: `{graph['active_node_id']}`", status)
        self.assertIn(f"Revision: {graph['revision']}", status)
        return result

    def test_quickstart_student_stops_before_reference_answer(self) -> None:
        output = self.root / "quick start"
        result = run_lab(output, "quickstart")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse((output / "REFERENCE_ANSWER.md").exists())
        graph = read_json(output / "project" / "research" / "state" / "graph.json")
        self.assertEqual(graph["active_node_id"], "idea-file-handoff")
        self.assertNotIn("review", {node["kind"] for node in graph["nodes"].values()})
        self.assert_state_handoff(output)

    def test_existing_output_is_never_overwritten(self) -> None:
        output = self.root / "keep me"
        output.mkdir()
        marker = output / "student.txt"
        marker.write_text("keep\n", encoding="utf-8")
        result = run_lab(output, "quickstart")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(marker.read_text(encoding="utf-8"), "keep\n")
        result = run_lab(output, "matched-pilot")
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
                summary = self.assert_state_handoff(output)
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
        self.assert_state_handoff(output)
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
        summary = self.assert_state_handoff(output)
        self.assertEqual(summary["expected_selection"], "B")
        self.assertEqual(summary["branches"]["a"]["verify_exit_code"], 1)
        self.assertEqual(summary["branches"]["c"]["verify_exit_code"], 0)
        graph = read_json(output / "project" / "research" / "state" / "graph.json")
        self.assertEqual(graph["nodes"]["review-branch-a"]["status"], "blocked")
        self.assertEqual(graph["nodes"]["review-branch-c"]["status"], "blocked")
        self.assertEqual(graph["active_node_id"], "analysis-branch-selection")
        self.assertEqual(
            summary["state_handoff"]["off_route_blockers"],
            ["experiment-branch-a", "review-branch-a", "review-branch-c"],
        )

    def test_reference_failed_review_keeps_experiment_actionable(self) -> None:
        output = self.root / "reference threshold miss"
        result = run_lab(output, "evidence", mode="reference", case="threshold-miss")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        summary = self.assert_state_handoff(output)
        graph = read_json(output / "project" / "research" / "state" / "graph.json")
        self.assertEqual(graph["active_node_id"], "experiment-evidence-demo")
        self.assertEqual(graph["nodes"]["review-evidence-demo"]["status"], "blocked")
        self.assertEqual(summary["state_handoff"]["blocked_followups"], ["review-evidence-demo"])
        status = (output / "project" / "STATUS.md").read_text(encoding="utf-8")
        self.assertIn("Blocked follow-ups from the active node: `review-evidence-demo`", status)
        self.assertNotIn("analysis-evidence-demo", graph["nodes"])

    def test_route_progression_ignores_supports_shortcut(self) -> None:
        output = self.root / "route"
        result = run_lab(output, "route")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        summary = self.assert_state_handoff(output)
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
        summary = self.assert_state_handoff(output)
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
        summary = self.assert_state_handoff(output)
        self.assertEqual(summary["stale_write_exit_code"], 4)
        self.assertEqual(summary["reloaded_revision"], summary["initial_revision"] + 1)
        self.assertEqual(summary["final_revision"], summary["reloaded_revision"] + 1)
        graph = read_json(output / "project" / "research" / "state" / "graph.json")
        self.assertIn("scout-session-a", graph["nodes"])
        self.assertIn("scout-session-b", graph["nodes"])

    def test_matched_pilot_prepares_four_cases_across_three_arms(self) -> None:
        output = self.root / "matched pilot"
        result = run_lab(output, "matched-pilot")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

        manifest = read_json(output / "pilot-manifest.json")
        self.assertEqual(manifest["status"], "prepared-not-run")
        self.assertEqual(
            manifest["cases"],
            ["engineering-continuity", "math-counterexample", "numerical-seeds", "idea-evaluation"],
        )
        self.assertEqual(manifest["arms"], ["plain", "scratchpad", "ds-lite"])
        self.assertEqual(len(manifest["runs"]), 12)

        for case_id in manifest["cases"]:
            for arm_id in manifest["arms"]:
                arm = output / "arms" / case_id / arm_id
                self.assertTrue((arm / "TASK.md").is_file())
                self.assertTrue((arm / "ARM_INSTRUCTIONS.md").is_file())

    def test_matched_pilot_keeps_task_materials_equal_and_arm_memory_distinct(self) -> None:
        output = self.root / "matched arm boundaries"
        result = run_lab(output, "matched-pilot")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

        for case_id in ("engineering-continuity", "math-counterexample", "numerical-seeds", "idea-evaluation"):
            arms = {arm_id: output / "arms" / case_id / arm_id for arm_id in ("plain", "scratchpad", "ds-lite")}
            task_texts = {(arm / "TASK.md").read_text(encoding="utf-8") for arm in arms.values()}
            self.assertEqual(len(task_texts), 1)
            material_snapshots = {
                arm_id: {
                    path.relative_to(arm / "materials").as_posix(): path.read_bytes()
                    for path in (arm / "materials").rglob("*")
                    if path.is_file()
                }
                for arm_id, arm in arms.items()
            }
            self.assertEqual(material_snapshots["plain"], material_snapshots["scratchpad"])
            self.assertEqual(material_snapshots["plain"], material_snapshots["ds-lite"])

            self.assertFalse((arms["plain"] / "NOTES.md").exists())
            self.assertFalse((arms["plain"] / "PROJECT.md").exists())
            self.assertTrue((arms["scratchpad"] / "NOTES.md").is_file())
            self.assertFalse((arms["scratchpad"] / "PROJECT.md").exists())
            self.assertTrue((arms["ds-lite"] / "PROJECT.md").is_file())
            self.assertTrue((arms["ds-lite"] / "STATUS.md").is_file())
            self.assertTrue((arms["ds-lite"] / "research" / "state" / "graph.json").is_file())
            self.assertTrue((arms["ds-lite"] / "research" / "work-unit.json").is_file())

    def test_matched_pilot_provides_runnable_cases_but_no_prefilled_results(self) -> None:
        output = self.root / "matched runnable cases"
        result = run_lab(output, "matched-pilot")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        fixture_env = os.environ.copy()
        fixture_env["PYTHONUTF8"] = "1"
        fixture_env["PYTHONDONTWRITEBYTECODE"] = "1"

        engineering = output / "arms" / "engineering-continuity" / "plain"
        self.assertTrue((engineering / "materials" / "slugger.py").is_file())
        self.assertTrue((output / "prompts" / "engineering-continuity" / "round-2.md").is_file())
        self.assertTrue((output / "prompts" / "engineering-continuity" / "round-3.md").is_file())
        completed = subprocess.run(
            [sys.executable, "-m", "unittest", "-v"],
            cwd=engineering / "materials",
            text=True,
            encoding="utf-8",
            errors="backslashreplace",
            capture_output=True,
            env=fixture_env,
        )
        self.assertEqual(completed.returncode, 1)
        self.assertIn("test_removes_punctuation_without_adding_a_separator", completed.stderr)

        math_arm = output / "arms" / "math-counterexample" / "plain"
        self.assertEqual(len((math_arm / "materials" / "observations.csv").read_text(encoding="utf-8").splitlines()), 41)
        math_result = math_arm / "math-search.json"
        completed = subprocess.run(
            [sys.executable, "materials/check_conjecture.py", "--max-n", "50", "--output", math_result.name],
            cwd=math_arm,
            text=True,
            encoding="utf-8",
            errors="backslashreplace",
            capture_output=True,
            env=fixture_env,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertEqual(read_json(math_result)["first_counterexample"]["n"], 40)

        numerical = output / "arms" / "numerical-seeds" / "plain"
        early_result = numerical / "early-summary.json"
        completed = subprocess.run(
            [sys.executable, "materials/run_simulation.py", "--seed-count", "2", "--output", early_result.name],
            cwd=numerical,
            text=True,
            encoding="utf-8",
            errors="backslashreplace",
            capture_output=True,
            env=fixture_env,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        numerical_result = numerical / "seed-summary.json"
        completed = subprocess.run(
            [sys.executable, "materials/run_simulation.py", "--seed-count", "20", "--output", numerical_result.name],
            cwd=numerical,
            text=True,
            encoding="utf-8",
            errors="backslashreplace",
            capture_output=True,
            env=fixture_env,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        early = read_json(early_result)
        expanded = read_json(numerical_result)
        self.assertLess(early["mean_a"], early["mean_b"])
        self.assertGreater(expanded["mean_a"], expanded["mean_b"])
        self.assertEqual(expanded["seed_count"], 20)

        ideas = read_json(output / "arms" / "idea-evaluation" / "plain" / "materials" / "candidates.json")
        self.assertEqual(len(ideas["candidates"]), 3)
        self.assertTrue((output / "arms" / "idea-evaluation" / "plain" / "materials" / "source-packet.md").is_file())

        score_rows = (output / "results" / "scores.csv").read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(score_rows), 1)
        self.assertIn("prepared-not-run", (output / "results" / "README.md").read_text(encoding="utf-8"))
        self.assertFalse(any(path.name == "REFERENCE_ANSWER.md" for path in (output / "arms").rglob("*")))

    def test_matched_pilot_has_auditable_manifest_and_separate_teaching_guides(self) -> None:
        output = self.root / "matched guides"
        result = run_lab(output, "matched-pilot")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

        for name in ("PILOT_README.md", "STUDENT_GUIDE.zh.md", "INSTRUCTOR_GUIDE.zh.md", "RUBRIC.csv"):
            self.assertTrue((output / name).is_file(), name)
        student = (output / "STUDENT_GUIDE.zh.md").read_text(encoding="utf-8")
        instructor = (output / "INSTRUCTOR_GUIDE.zh.md").read_text(encoding="utf-8")
        self.assertIn("PowerShell", student)
        self.assertIn("WSL", student)
        self.assertIn("Set-Location arms/numerical-seeds/plain", student)
        self.assertIn("python materials/run_simulation.py --seed-count 20 --output expanded.json", student)
        self.assertIn("教师材料", instructor)
        self.assertIn("不作统计显著性宣称", instructor)
        self.assertIn("明确授权", instructor)

        manifest = read_json(output / "pilot-manifest.json")
        run_ids = {run["run_id"] for run in manifest["runs"]}
        self.assertEqual(len(run_ids), 12)
        for case_id in manifest["cases"]:
            case_runs = [run for run in manifest["runs"] if run["case"] == case_id]
            self.assertEqual(len({run["input_digest"] for run in case_runs}), 1)
            for run in case_runs:
                self.assertEqual(run["status"], "pending")
                self.assertFalse(Path(run["workspace"]).is_absolute())
                self.assertTrue(run["result_ref"].startswith("results/"))

        generated_text = "\n".join(
            path.read_text(encoding="utf-8")
            for path in output.rglob("*")
            if path.is_file()
        )
        self.assertNotIn(str(output.resolve()), generated_text)
        for forbidden in ("hidden_reasoning", "chain_of_thought", "api_key", "password", "secret", "token"):
            self.assertNotIn(f'"{forbidden}"', generated_text.lower())

    def test_matched_pilot_rejects_reference_mode_instead_of_leaking_answers(self) -> None:
        output = self.root / "matched reference"
        result = run_lab(output, "matched-pilot", mode="reference")
        self.assertEqual(result.returncode, 1)
        self.assertIn("student workspaces", result.stderr)
        self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
