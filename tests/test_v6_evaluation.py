#!/usr/bin/env python3
"""Tests for Cross-domain Evaluation Framework (PR 7)."""

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from plugins.deepscientist_lite_import_shim import ds_lite_v6_evaluation as ev


class EvaluationCreationTests(unittest.TestCase):
    def test_create_evaluation(self):
        """Should create a valid evaluation framework."""
        evaluation = ev.create_evaluation(
            evaluation_id="eval-001",
            mechanisms=["task-assessment", "claim-ledger"],
            task_domains=["finance", "engineering", "systematic-review"],
            conditions={
                "B0_condition_freeze": {"frozen": True, "model": "gpt-4"},
            },
        )
        self.assertEqual(evaluation["evaluation_id"], "eval-001")
        self.assertEqual(len(evaluation["mechanisms"]), 2)
        self.assertEqual(len(evaluation["task_domains"]), 3)
        self.assertEqual(evaluation["status"], "draft")

    def test_invalid_task_domain_rejected(self):
        """Invalid task domain should be rejected."""
        with self.assertRaises(ev.EvaluationError):
            ev.create_evaluation(
                evaluation_id="eval-002",
                mechanisms=["task-assessment"],
                task_domains=["invalid-domain"],
                conditions={},
            )


class PhaseResultRecordingTests(unittest.TestCase):
    def setUp(self):
        self.evaluation = ev.create_evaluation(
            evaluation_id="eval-003",
            mechanisms=["task-assessment"],
            task_domains=["finance", "engineering", "systematic-review"],
            conditions={"B0_condition_freeze": {"frozen": True}},
        )

    def test_record_phase_result(self):
        """Should record phase results."""
        result = ev.record_phase_result(
            self.evaluation,
            "B1-deterministic-fixtures",
            {
                "status": "pass",
                "metrics": {"recall": 0.95, "precision": 0.90},
                "evidence_refs": ["evidence/b1.json"],
                "notes": "All deterministic fixtures passed",
            },
        )
        self.assertEqual(result["status"], "pass")
        self.assertIn("B1-deterministic-fixtures", self.evaluation["phase_results"])

    def test_invalid_phase_rejected(self):
        """Invalid phase should be rejected."""
        with self.assertRaises(ev.EvaluationError):
            ev.record_phase_result(
                self.evaluation,
                "invalid-phase",
                {"status": "pass"},
            )

    def test_invalid_status_rejected(self):
        """Invalid status should be rejected."""
        with self.assertRaises(ev.EvaluationError):
            ev.record_phase_result(
                self.evaluation,
                "B1-deterministic-fixtures",
                {"status": "invalid"},
            )


class DecisionGenerationTests(unittest.TestCase):
    def setUp(self):
        self.evaluation = ev.create_evaluation(
            evaluation_id="eval-004",
            mechanisms=["task-assessment", "claim-ledger"],
            task_domains=["finance", "engineering", "systematic-review"],
            conditions={"B0_condition_freeze": {"frozen": True}},
        )

    def test_generate_decision_all_pass(self):
        """Should generate release decision when all phases pass."""
        for phase in ev.EVALUATION_PHASES:
            ev.record_phase_result(
                self.evaluation,
                phase,
                {"status": "pass", "metrics": {}, "evidence_refs": ["ref"]},
            )
        decision = ev.generate_decision(self.evaluation)
        self.assertEqual(decision["summary"]["released"], 2)
        self.assertEqual(decision["summary"]["rejected"], 0)
        self.assertIn("decision_digest", decision)

    def test_generate_decision_mixed_results(self):
        """Should generate mixed decisions when phases have mixed results."""
        # Pass some phases, fail others
        phases = list(ev.EVALUATION_PHASES)
        for i, phase in enumerate(phases):
            status = "pass" if i < 4 else "fail"
            ev.record_phase_result(
                self.evaluation,
                phase,
                {"status": status, "metrics": {}, "evidence_refs": []},
            )
        decision = ev.generate_decision(self.evaluation)
        # With 4 passes and 3 fails, should be shadow or revise
        for d in decision["decisions"]:
            self.assertIn(d["decision"], {"shadow", "revise", "reject"})

    def test_generate_decision_all_fail(self):
        """Should generate reject decision when all phases fail."""
        for phase in ev.EVALUATION_PHASES:
            ev.record_phase_result(
                self.evaluation,
                phase,
                {"status": "fail", "metrics": {}, "evidence_refs": []},
            )
        decision = ev.generate_decision(self.evaluation)
        self.assertEqual(decision["summary"]["rejected"], 2)
        self.assertEqual(decision["summary"]["released"], 0)

    def test_decision_has_evidence_digests(self):
        """Decision should include evidence digests."""
        for phase in ev.EVALUATION_PHASES:
            ev.record_phase_result(
                self.evaluation,
                phase,
                {"status": "pass", "metrics": {}, "evidence_refs": ["evidence.json"]},
            )
        decision = ev.generate_decision(self.evaluation)
        for d in decision["decisions"]:
            self.assertGreater(len(d["evidence_digests"]), 0)


class EvaluationValidationTests(unittest.TestCase):
    def test_valid_evaluation_passes(self):
        """A valid evaluation should pass validation."""
        evaluation = ev.create_evaluation(
            evaluation_id="eval-005",
            mechanisms=["task-assessment"],
            task_domains=["finance", "engineering", "systematic-review"],
            conditions={"B0_condition_freeze": {"frozen": True}},
        )
        result = ev.validate_evaluation(evaluation)
        self.assertEqual(result["verdict"], "pass")

    def test_insufficient_task_domains_blocked(self):
        """Fewer than 3 task domains should be blocked."""
        evaluation = ev.create_evaluation(
            evaluation_id="eval-006",
            mechanisms=["task-assessment"],
            task_domains=["finance", "engineering"],
            conditions={"B0_condition_freeze": {"frozen": True}},
        )
        result = ev.validate_evaluation(evaluation)
        self.assertEqual(result["verdict"], "blocked")
        self.assertIn("insufficient_task_domains", result["rule_ids"])

    def test_unfrozen_conditions_blocked(self):
        """Unfrozen B0 conditions should be blocked."""
        evaluation = ev.create_evaluation(
            evaluation_id="eval-007",
            mechanisms=["task-assessment"],
            task_domains=["finance", "engineering", "systematic-review"],
            conditions={"B0_condition_freeze": {"frozen": False}},
        )
        result = ev.validate_evaluation(evaluation)
        self.assertEqual(result["verdict"], "blocked")
        self.assertIn("B0_conditions_not_frozen", result["rule_ids"])


if __name__ == "__main__":
    unittest.main()