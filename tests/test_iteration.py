from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
ITERATION_SCRIPT = (
    REPO_ROOT / "plugins" / "deepscientist-lite" / "scripts" / "ds_lite_iteration.py"
)
STATE_SCRIPT = REPO_ROOT / "plugins" / "deepscientist-lite" / "scripts" / "ds_lite_state.py"
SCRIPT_DIR = ITERATION_SCRIPT.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import ds_lite_iteration


def complete_iteration() -> dict:
    return {
        "schema_version": "ds-lite.iteration.v1",
        "iteration_id": "iteration-route-a-001",
        "work_unit_id": "work-route-a",
        "profile_id": "core-planning",
        "execution_mode": "inline",
        "status": "completed",
        "selected_skill": "ds-lite-idea",
        "expected_revision": 3,
        "before_revision": 3,
        "after_revision": 4,
        "action": {
            "kind": "idea",
            "summary": "Compare the bounded candidate routes.",
            "prediction": "One candidate will have a cheaper discriminating probe.",
            "falsification_condition": "No candidate has a probe within the declared budget.",
            "resource_limits": [{"dimension": "actions", "unit": "count", "value": 1}],
            "stop_condition": "Stop after one comparison and status update.",
            "extensions": {},
        },
        "input_refs": ["PROJECT.md", "research/work-unit.json"],
        "output_refs": ["research/artifacts/frontier-decision-route-a.md"],
        "graph_changes": [
            {
                "kind": "add-node",
                "subject_id": "idea-route-a",
                "summary": "Added one testable idea branch.",
                "extensions": {},
            }
        ],
        "validations": [
            {
                "command": "python plugins/deepscientist-lite/scripts/ds_lite_state.py mission --root .",
                "status": "pass",
                "summary": "Mission Board rendered at revision 4.",
                "extensions": {},
            }
        ],
        "stop_reason": "action-completed",
        "reflection": {
            "observed_outcomes": ["The selected probe fits the one-action budget."],
            "hypothesis_updates": [
                {
                    "hypothesis_id": "idea-route-a",
                    "status": "untested",
                    "evidence_refs": ["research/artifacts/frontier-decision-route-a.md"],
                    "summary": "Selected for a discriminating probe; no claim evidence yet.",
                    "extensions": {},
                }
            ],
            "expectation_gap": "Selection succeeded, but novelty remains unknown.",
            "negative_results": [
                {
                    "summary": "The discarded route exceeded the action budget.",
                    "evidence_refs": ["research/artifacts/frontier-decision-route-a.md"],
                    "extensions": {},
                }
            ],
            "responsibility": {
                "authorization_basis": "User requested one bounded implementation iteration.",
                "boundaries_respected": ["No external execution or irreversible action."],
                "unresolved_obligations": ["Run the selected probe before claim promotion."],
                "extensions": {},
            },
            "learned_boundaries": ["Factor Card selection is not typed evidence."],
            "next_candidates": [
                {
                    "hypothesis_id": "idea-route-a",
                    "title": "Route A",
                    "status": "untested",
                    "minimal_test": "Run one single-axis comparison.",
                    "extensions": {},
                }
            ],
            "minimal_discriminating_test": "Run one single-axis comparison and retain a negative result.",
            "extensions": {},
        },
        "user_report": {
            "summary": "Compared the candidates and selected one bounded probe.",
            "files_changed": ["research/artifacts/frontier-decision-route-a.md"],
            "validation_summary": "Mission Board validation passed at revision 4.",
            "failure_layer": "none",
            "unverified": ["The selected mechanism has not been experimentally tested."],
            "hypothesis_changes": ["idea-route-a remains untested and is now selected."],
            "next_action": "Run the minimal comparison.",
            "decision_needed": "none",
            "extensions": {},
        },
        "started_at": "2026-07-17T01:00:00Z",
        "completed_at": "2026-07-17T01:04:00Z",
        "extensions": {},
    }


def initialize_project(root: Path) -> None:
    completed = subprocess.run(
        [
            sys.executable,
            str(STATE_SCRIPT),
            "init",
            "--root",
            str(root),
            "--title",
            "Iteration test",
            "--question",
            "Does one bounded action remain recoverable?",
        ],
        cwd=REPO_ROOT,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
    )
    if completed.returncode != 0:
        raise AssertionError(completed.stdout + completed.stderr)


def terminal_result(after_revision: int) -> dict:
    payload = complete_iteration()
    return {
        "status": payload["status"],
        "after_revision": after_revision,
        "output_refs": payload["output_refs"],
        "graph_changes": payload["graph_changes"],
        "validations": payload["validations"],
        "stop_reason": payload["stop_reason"],
        "reflection": payload["reflection"],
        "user_report": payload["user_report"],
        "completed_at": payload["completed_at"],
        "extensions": {},
    }


class IterationEntrypointTests(unittest.TestCase):
    def test_iteration_helper_exists_as_an_independent_runtime_module(self) -> None:
        self.assertTrue(ITERATION_SCRIPT.is_file(), "missing ds_lite_iteration.py")


class IterationSchemaTests(unittest.TestCase):
    def test_iteration_accepts_complete_object_and_extensions(self) -> None:
        payload = complete_iteration()
        payload["extensions"] = {"example.org/report-lane": "teaching"}
        self.assertEqual(ds_lite_iteration.validate_iteration(payload), payload)

    def test_iteration_rejects_unregistered_selected_skill(self) -> None:
        payload = complete_iteration()
        payload["selected_skill"] = "ds-lite-made-up"
        with self.assertRaisesRegex(ds_lite_iteration.IterationError, "selected_skill"):
            ds_lite_iteration.validate_iteration(payload)

    def test_iteration_rejects_unregistered_and_legacy_action_kinds(self) -> None:
        payload = complete_iteration()
        payload["action"]["kind"] = "office-task"
        with self.assertRaisesRegex(ds_lite_iteration.IterationError, "action.kind"):
            ds_lite_iteration.validate_iteration(payload)

        payload["action"]["kind"] = "exploit"
        with self.assertRaisesRegex(ds_lite_iteration.IterationError, "map legacy exploit to execute"):
            ds_lite_iteration.validate_iteration(payload)

    def test_iteration_rejects_missing_field(self) -> None:
        payload = complete_iteration()
        payload.pop("reflection")
        with self.assertRaisesRegex(ds_lite_iteration.IterationError, "missing fields: reflection"):
            ds_lite_iteration.validate_iteration(payload)

    def test_iteration_rejects_wrong_enum(self) -> None:
        payload = complete_iteration()
        payload["status"] = "auto-retried"
        with self.assertRaisesRegex(ds_lite_iteration.IterationError, "status"):
            ds_lite_iteration.validate_iteration(payload)

    def test_iteration_rejects_path_escape(self) -> None:
        payload = complete_iteration()
        payload["output_refs"] = ["../outside/report.md"]
        with self.assertRaisesRegex(ds_lite_iteration.IterationError, "output_refs"):
            ds_lite_iteration.validate_iteration(payload)

    def test_iteration_rejects_sensitive_or_hidden_reasoning_fields(self) -> None:
        payload = complete_iteration()
        payload["reflection"]["extensions"] = {"chain_of_thought": "must not persist"}
        with self.assertRaisesRegex(ds_lite_iteration.IterationError, "sensitive or hidden-reasoning"):
            ds_lite_iteration.validate_iteration(payload)

    def test_iteration_rejects_id_conflicts(self) -> None:
        payload = complete_iteration()
        payload["iteration_id"] = payload["work_unit_id"]
        with self.assertRaisesRegex(ds_lite_iteration.IterationError, "must differ"):
            ds_lite_iteration.validate_iteration(payload)

    def test_iteration_rejects_unknown_fields(self) -> None:
        payload = complete_iteration()
        payload["raw_conversation"] = "not allowed"
        with self.assertRaisesRegex(ds_lite_iteration.IterationError, "unsupported fields: raw_conversation"):
            ds_lite_iteration.validate_iteration(payload)

    def test_iteration_allows_forward_compatible_nested_extensions(self) -> None:
        payload = complete_iteration()
        payload = copy.deepcopy(payload)
        payload["reflection"]["hypothesis_updates"][0]["extensions"] = {
            "example.org/calibration": "provisional"
        }
        self.assertEqual(ds_lite_iteration.validate_iteration(payload), payload)

    def test_measured_hypothesis_status_requires_evidence_refs(self) -> None:
        payload = complete_iteration()
        payload["reflection"]["hypothesis_updates"][0]["status"] = "supported"
        payload["reflection"]["hypothesis_updates"][0]["evidence_refs"] = []
        with self.assertRaisesRegex(ds_lite_iteration.IterationError, "supported.*evidence_refs"):
            ds_lite_iteration.validate_iteration(payload)

    def test_negative_result_requires_an_evidence_ref(self) -> None:
        payload = complete_iteration()
        payload["reflection"]["negative_results"][0]["evidence_refs"] = []
        with self.assertRaisesRegex(ds_lite_iteration.IterationError, "negative_results.*evidence_refs"):
            ds_lite_iteration.validate_iteration(payload)


class IterationLifecycleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="ds-lite-iteration-"))
        initialize_project(self.root)

    def test_initialize_registers_running_iteration_before_action(self) -> None:
        payload = ds_lite_iteration.initialize_iteration(
            self.root,
            iteration_id="iteration-intake-001",
            selected_skill="ds-lite-intake",
            action=complete_iteration()["action"],
            input_refs=["PROJECT.md", "research/work-unit.json"],
            expected_revision=0,
        )
        self.assertEqual(payload["status"], "running")
        self.assertEqual(payload["before_revision"], 0)
        self.assertIsNone(payload["after_revision"])
        self.assertEqual(payload["reflection"]["hypothesis_updates"], [])
        ref = "research/iterations/iteration-intake-001.json"
        self.assertEqual(payload["extensions"]["iteration_ref"], ref)
        saved = json.loads((self.root / ref).read_text(encoding="utf-8"))
        self.assertEqual(saved, payload)
        work_unit = json.loads((self.root / "research" / "work-unit.json").read_text(encoding="utf-8"))
        self.assertEqual(work_unit["active_iteration_ref"], ref)

    def test_initialize_rejects_stale_revision_without_writing(self) -> None:
        with self.assertRaisesRegex(ds_lite_iteration.IterationError, "stale revision"):
            ds_lite_iteration.initialize_iteration(
                self.root,
                iteration_id="iteration-stale-001",
                selected_skill="ds-lite-iterate",
                action=complete_iteration()["action"],
                input_refs=["PROJECT.md"],
                expected_revision=1,
            )
        self.assertFalse((self.root / "research" / "iterations" / "iteration-stale-001.json").exists())

    def test_finalize_and_verify_require_current_context_and_single_terminal_transition(self) -> None:
        running = ds_lite_iteration.initialize_iteration(
            self.root,
            iteration_id="iteration-route-a-001",
            selected_skill="ds-lite-idea",
            action=complete_iteration()["action"],
            input_refs=["PROJECT.md"],
            expected_revision=0,
        )
        ref = running["extensions"]["iteration_ref"]
        finished = ds_lite_iteration.finalize_iteration(self.root, ref, terminal_result(0))
        self.assertEqual(finished["status"], "completed")
        self.assertEqual(ds_lite_iteration.verify_iteration(self.root, ref), finished)
        with self.assertRaisesRegex(ds_lite_iteration.IterationError, "already terminal"):
            ds_lite_iteration.finalize_iteration(self.root, ref, terminal_result(0))

        work_unit_path = self.root / "research" / "work-unit.json"
        work_unit = json.loads(work_unit_path.read_text(encoding="utf-8"))
        work_unit["profile_id"] = "changed-profile"
        work_unit_path.write_text(json.dumps(work_unit, indent=2) + "\n", encoding="utf-8")
        with self.assertRaisesRegex(ds_lite_iteration.IterationError, "profile_id does not match"):
            ds_lite_iteration.verify_iteration(self.root, ref)

    def test_cli_exposes_init_finalize_and_verify(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(ITERATION_SCRIPT), "--help"],
            cwd=REPO_ROOT,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        for command in ("init", "finalize", "verify"):
            self.assertIn(command, completed.stdout)

if __name__ == "__main__":
    unittest.main()
