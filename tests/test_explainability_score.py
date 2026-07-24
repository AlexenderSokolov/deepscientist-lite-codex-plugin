import unittest

from teaching.explainability_score import ExplainabilityError, assess_case


def _case(**overrides):
    value = {
        "expected_applicability": "applicable",
        "claimed_applicability": "applicable",
        "expected_skill": "ds-lite-intake",
        "claimed_skill": "ds-lite-intake",
        "evidence_refs": ["PROJECT.md", "STATUS.md"],
        "observed_refs": ["PROJECT.md", "STATUS.md"],
        "action": "read the project state",
        "stop_condition": "stop after one state report",
        "verification": [
            {"command": "python tools/validation/validate_repo.py", "status": "pass", "ref": "research/artifacts/validation.md"}
        ],
        "unverified": ["fresh host hook loading"],
        "next_action": "ask whether to initialize the work unit",
        "decision_needed": "user approval",
        "artifact_refs": ["research/artifacts/intake.md"],
        "unsupported_completion_claims": 0,
        "status": "completed",
    }
    value.update(overrides)
    return value


class ExplainabilityScoreTests(unittest.TestCase):
    def test_applicable_case_requires_evidence_and_user_boundary(self):
        result = assess_case(_case())
        self.assertEqual(result["applicability_accuracy"], 1)
        self.assertEqual(result["activation_false_positive"], 0)
        self.assertEqual(result["activation_false_negative"], 0)
        self.assertEqual(result["rationale_evidence_coverage"], 4)
        self.assertEqual(result["verification_traceability"], 3)
        self.assertEqual(result["user_decision_clarity"], 3)
        self.assertEqual(result["artifact_recoverability"], 1)

    def test_not_applicable_case_detects_false_positive_and_forbidden_artifact(self):
        result = assess_case(
            _case(
                expected_applicability="not-applicable",
                claimed_applicability="applicable",
                expected_skill="",
                claimed_skill="ds-lite-intake",
                evidence_refs=[],
                observed_refs=[],
                action="initialize research state",
                stop_condition="",
                verification=[],
                unverified=[],
                next_action="",
                decision_needed="",
                artifact_refs=["research/STATUS.md"],
                status="completed",
            )
        )
        self.assertEqual(result["applicability_accuracy"], 0)
        self.assertEqual(result["activation_false_positive"], 1)
        self.assertEqual(result["artifact_recoverability"], 0)
        self.assertGreaterEqual(result["unsupported_completion_count"], 1)

    def test_missing_verification_and_absolute_refs_are_rejected(self):
        with self.assertRaises(ExplainabilityError):
            assess_case(_case(observed_refs=["C:/secret/STATUS.md"]))

    def test_unknown_fields_and_invalid_applicability_are_rejected(self):
        with self.assertRaises(ExplainabilityError):
            assess_case(_case(unexpected="value"))
        with self.assertRaises(ExplainabilityError):
            assess_case(_case(expected_applicability="maybe"))


if __name__ == "__main__":
    unittest.main()
