#!/usr/bin/env python3
"""Tests for Task Assessment / Answerability Gate (PR 1)."""

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from plugins.deepscientist_lite_import_shim import ds_lite_assessment


class TaskAssessmentTests(unittest.TestCase):
    def test_diagnostic_task_cannot_enter_confirmatory(self):
        """Rule: diagnostic task cannot reach confirmatory evidence level."""
        assessment = ds_lite_assessment.create_assessment(
            assessment_id="asmt-001",
            work_unit_id="wu-001",
            task_kind="diagnostic",
            question="Does X improve Y?",
            input_roles=["analyst"],
            resources={"dataset": "available"},
            permissions={"compute": "granted"},
            reachable_evidence_level="confirmatory",
            answerability_status="answerable",
            non_claims=["Cannot claim generalizability"],
            preconditions=["Dataset D is available"],
        )
        result = ds_lite_assessment.validate_task_assessment(assessment)
        self.assertEqual(result["verdict"], "blocked")
        self.assertIn("diagnostic_cannot_be_confirmatory", result["rule_ids"])

    def test_not_answerable_task_is_blocked(self):
        """Rule: not-answerable tasks must be blocked."""
        assessment = ds_lite_assessment.create_assessment(
            assessment_id="asmt-002",
            work_unit_id="wu-002",
            task_kind="exploratory",
            question="What is the meaning of life?",
            input_roles=["analyst"],
            resources={"dataset": "missing"},
            permissions={"compute": "denied"},
            reachable_evidence_level="none",
            answerability_status="not-answerable",
            non_claims=[],
            preconditions=[],
        )
        result = ds_lite_assessment.validate_task_assessment(assessment)
        self.assertEqual(result["verdict"], "blocked")
        self.assertIn("not_answerable_blocked", result["rule_ids"])

    def test_needs_human_is_blocked(self):
        """Rule: needs-human tasks must be blocked."""
        assessment = ds_lite_assessment.create_assessment(
            assessment_id="asmt-003",
            work_unit_id="wu-003",
            task_kind="confirmatory",
            question="Is this ethically acceptable?",
            input_roles=["analyst"],
            resources={"dataset": "available"},
            permissions={"ethics": "unknown"},
            reachable_evidence_level="confirmatory",
            answerability_status="needs-human",
            non_claims=["Cannot claim universal applicability"],
            preconditions=["Ethics board approval"],
        )
        result = ds_lite_assessment.validate_task_assessment(assessment)
        self.assertEqual(result["verdict"], "blocked")
        self.assertIn("needs_human_blocked", result["rule_ids"])

    def test_missing_resources_triggers_warning(self):
        """Rule: missing resources trigger warning."""
        assessment = ds_lite_assessment.create_assessment(
            assessment_id="asmt-004",
            work_unit_id="wu-004",
            task_kind="pilot",
            question="Does X improve Y on dataset D?",
            input_roles=["analyst"],
            resources={"dataset_d": "missing"},
            permissions={"compute": "granted"},
            reachable_evidence_level="pilot",
            answerability_status="partially-answerable",
            non_claims=["Cannot claim causation"],
            preconditions=["Dataset D can be obtained"],
        )
        result = ds_lite_assessment.validate_task_assessment(assessment)
        self.assertIn("missing_resources", result["rule_ids"])
        self.assertIn(result["verdict"], {"warning", "blocked"})

    def test_confirmatory_requires_non_claims(self):
        """Rule: confirmatory tasks must have non_claims."""
        assessment = ds_lite_assessment.create_assessment(
            assessment_id="asmt-005",
            work_unit_id="wu-005",
            task_kind="confirmatory",
            question="Does X cause Y?",
            input_roles=["analyst"],
            resources={"dataset": "available"},
            permissions={"compute": "granted"},
            reachable_evidence_level="confirmatory",
            answerability_status="answerable",
            non_claims=[],
            preconditions=["Pre-registration completed"],
        )
        result = ds_lite_assessment.validate_task_assessment(assessment)
        self.assertEqual(result["verdict"], "blocked")
        self.assertIn("confirmatory_requires_non_claims", result["rule_ids"])

    def test_valid_assessment_passes(self):
        """A valid assessment should pass."""
        assessment = ds_lite_assessment.create_assessment(
            assessment_id="asmt-006",
            work_unit_id="wu-006",
            task_kind="pilot",
            question="Does X improve Y?",
            input_roles=["analyst"],
            resources={"dataset": "available"},
            permissions={"compute": "granted"},
            reachable_evidence_level="pilot",
            answerability_status="answerable",
            non_claims=["Cannot claim generalizability beyond dataset D"],
            preconditions=["Dataset D is available", "Compute is allocated"],
        )
        result = ds_lite_assessment.validate_task_assessment(assessment)
        self.assertEqual(result["verdict"], "pass")
        self.assertIn("assessment_digest", result)

    def test_assessment_digest_is_stable(self):
        """Assessment digest should be stable for the same input."""
        assessment1 = ds_lite_assessment.create_assessment(
            assessment_id="asmt-007",
            work_unit_id="wu-007",
            task_kind="diagnostic",
            question="Does X improve Y?",
            input_roles=["analyst"],
            resources={"dataset": "available"},
            permissions={"compute": "granted"},
            reachable_evidence_level="diagnostic",
            answerability_status="answerable",
            non_claims=[],
            preconditions=["Dataset D is available"],
        )
        assessment2 = dict(assessment1)
        result1 = ds_lite_assessment.validate_task_assessment(assessment1)
        result2 = ds_lite_assessment.validate_task_assessment(assessment2)
        self.assertEqual(result1["assessment_digest"], result2["assessment_digest"])


if __name__ == "__main__":
    unittest.main()