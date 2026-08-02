from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "teaching"))

import matched_effect  # noqa: E402


CASES = ("engineering-continuity", "math-counterexample", "numerical-seeds", "idea-evaluation")
ARMS = ("plain", "scratchpad", "ds-lite")
EXPRESSION_METRICS = (
    "factual_grounding",
    "verification_explanation",
    "authorization_boundary",
    "unverified_clarity",
    "next_action_clarity",
)


class MatchedEffectTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="ds-lite-matched-effect-"))
        (self.root / "results" / "executions").mkdir(parents=True)
        scores = []
        calls = []
        for case in CASES:
            for arm in ARMS:
                call_id = f"{case}--{arm}--r1"
                result_ref = f"results/executions/{call_id}.json"
                calls.append({"call_id": call_id, "case": case, "arm": arm, "result_ref": result_ref})
                (self.root / result_ref).write_text(
                    json.dumps(
                        {
                            "status": "completed",
                            "final_message": f"Evidence-backed public report for {case}.",
                            "usage": {"total_tokens": 10},
                            "result_refs": [result_ref],
                        }
                    ),
                    encoding="utf-8",
                )
                scores.append(
                    {
                        "case": case,
                        "arm": arm,
                        "status": "auto-scored-awaiting-blind-review",
                        "task_correctness": 4 if arm == "ds-lite" else 3,
                        "evidence_traceability": 4 if arm == "ds-lite" else 2,
                        "route_recovery": 4 if arm == "ds-lite" else 2,
                        "state_omission_count": 0 if arm == "ds-lite" else 1,
                        "negative_result_retained": 1,
                        "cost_units": 10,
                    }
                )
        (self.root / "execution-plan.json").write_text(json.dumps({"pilot_id": "gated-03", "calls": calls}), encoding="utf-8")
        (self.root / "results" / "score-report.json").write_text(
            json.dumps({"status": "auto-scored-awaiting-blind-review", "scores": scores}), encoding="utf-8"
        )

    def _write_review_execution(self, *, mapping_available: bool = False) -> Path:
        path = self.root / "results" / "blind-review-execution.json"
        path.write_text(
            json.dumps(
                {
                    "schema_version": "ds-lite.blind-review-execution.v1",
                    "status": "completed",
                    "call_count": 1,
                    "input_refs": [
                        "blind-review/blind-items.json",
                        "blind-review/review-schema.json",
                    ],
                    "output_ref": "blind-review/blind-scores.json",
                    "mapping_available_to_reviewer": mapping_available,
                    "usage": {"total_tokens": 20},
                }
            ),
            encoding="utf-8",
        )
        return path

    def test_blind_package_hides_arm_mapping_and_refuses_overwrite(self) -> None:
        blind_root = self.root / "blind-review"
        result = matched_effect.prepare_blind_package(self.root, blind_root, seed="fixed-seed")
        self.assertEqual(result["item_count"], 12)
        self.assertTrue((self.root / "results" / "blind-map.json").is_file())
        package_text = "\n".join(path.read_text(encoding="utf-8") for path in blind_root.rglob("*") if path.is_file())
        self.assertNotIn('"arm"', package_text)
        self.assertNotIn('"ds-lite"', package_text)
        self.assertNotIn('"plain"', package_text)
        self.assertNotIn('"scratchpad"', package_text)
        blind_items = json.loads((blind_root / "blind-items.json").read_text(encoding="utf-8"))["items"]
        self.assertNotIn("final_message", blind_items[0])
        self.assertEqual(
            set(blind_items[0]["reviewable_responses"][0]),
            {"public_response", "text_sha256"},
        )
        self.assertIn("Evidence-backed public report", blind_items[0]["reviewable_responses"][0]["public_response"])
        with self.assertRaises(matched_effect.MatchedEffectError):
            matched_effect.prepare_blind_package(self.root, blind_root, seed="fixed-seed")

    def _set_first_final_message(self, message: str) -> None:
        first_receipt = next((self.root / "results" / "executions").glob("*.json"))
        payload = json.loads(first_receipt.read_text(encoding="utf-8"))
        payload["final_message"] = message
        first_receipt.write_text(json.dumps(payload), encoding="utf-8")

    def _assert_sensitive_final_message_rejected(self, message: str) -> None:
        self._set_first_final_message(message)
        with self.assertRaisesRegex(matched_effect.MatchedEffectError, "sensitive"):
            matched_effect.prepare_blind_package(self.root, self.root / "blind-review", seed="fixed-seed")
        self.assertFalse((self.root / "blind-review").exists())
        self.assertFalse((self.root / "results" / "blind-map.json").exists())

    def test_blind_package_rejects_raw_execution_fields(self) -> None:
        first_receipt = next((self.root / "results" / "executions").glob("*.json"))
        payload = json.loads(first_receipt.read_text(encoding="utf-8"))
        marker = "SECRET-MARKER-RAW-FINAL-MESSAGE"
        payload["raw_stderr"] = marker
        first_receipt.write_text(json.dumps(payload), encoding="utf-8")
        with self.assertRaisesRegex(matched_effect.MatchedEffectError, "sensitive"):
            matched_effect.prepare_blind_package(self.root, self.root / "blind-review", seed="fixed-seed")

    def test_blind_package_rejects_secret_marker_in_final_message(self) -> None:
        self._assert_sensitive_final_message_rejected("Evidence verified. SECRET-MARKER-RAW-FINAL-MESSAGE")

    def test_blind_package_rejects_url_in_final_message(self) -> None:
        self._assert_sensitive_final_message_rejected("See https://private.example/report for evidence.")

    def test_blind_package_rejects_absolute_path_in_final_message(self) -> None:
        self._assert_sensitive_final_message_rejected(r"Evidence stored at C:\Users\private\result.json.")

    def test_public_slash_separator_is_not_misclassified_as_posix_path(self) -> None:
        result = matched_effect._reviewable_public_response("Compare the admin / api reserved slugs.")
        self.assertIn("public_response", result)
        with self.assertRaisesRegex(matched_effect.MatchedEffectError, "sensitive"):
            matched_effect._reviewable_public_response("Evidence stored at /home/private/result.json.")

    def test_blind_package_rejects_credential_marker_in_final_message(self) -> None:
        self._assert_sensitive_final_message_rejected("Authorization: Bearer sk-private-credential-marker")

    def test_effect_report_uses_paired_deltas_dz_and_direction_without_p_values(self) -> None:
        blind_root = self.root / "blind-review"
        matched_effect.prepare_blind_package(self.root, blind_root, seed="fixed-seed")
        mapping = json.loads((self.root / "results" / "blind-map.json").read_text(encoding="utf-8"))
        reviews = []
        for item in mapping["items"]:
            value = 4 if item["arm"] == "ds-lite" else 2 if item["arm"] == "scratchpad" else 1
            review = {"alias": item["alias"], "unsupported_completion_count": 0 if item["arm"] == "ds-lite" else 1}
            review.update({metric: value for metric in EXPRESSION_METRICS})
            reviews.append(review)
        review_path = blind_root / "blind-scores.json"
        review_path.write_text(json.dumps({"schema_version": "ds-lite.blind-expression-score.v1", "scores": reviews}), encoding="utf-8")

        report = matched_effect.build_effect_report(
            self.root,
            mapping_path=self.root / "results" / "blind-map.json",
            blind_scores_path=review_path,
            review_execution_path=self._write_review_execution(),
            output_path=self.root / "results" / "matched-effect.json",
        )

        self.assertEqual(report["schema_version"], "ds-lite.matched-effect.v1")
        self.assertEqual(report["status"], "descriptive-improvement-supported")
        self.assertEqual(report["comparisons"]["plain"]["factual_grounding"]["favorable_cases"], 4)
        self.assertGreater(report["comparisons"]["plain"]["factual_grounding"]["paired_mean_delta"], 0)
        self.assertIn("standardized_dz", report["comparisons"]["plain"]["factual_grounding"])
        self.assertNotIn("p_value", json.dumps(report))
        self.assertEqual(report["blind_review_call_count"], 1)
        self.assertFalse(report["mapping_available_to_reviewer"])

    def test_effect_report_freezes_when_mapping_was_available_to_reviewer(self) -> None:
        blind_root = self.root / "blind-review"
        matched_effect.prepare_blind_package(self.root, blind_root, seed="fixed-seed")
        mapping = json.loads((self.root / "results" / "blind-map.json").read_text(encoding="utf-8"))
        reviews = []
        for item in mapping["items"]:
            review = {"alias": item["alias"], "unsupported_completion_count": 0}
            review.update({metric: 3 for metric in EXPRESSION_METRICS})
            reviews.append(review)
        review_path = blind_root / "blind-scores.json"
        review_path.write_text(
            json.dumps({"schema_version": "ds-lite.blind-expression-score.v1", "scores": reviews}),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(matched_effect.MatchedEffectError, "mapping"):
            matched_effect.build_effect_report(
                self.root,
                mapping_path=self.root / "results" / "blind-map.json",
                blind_scores_path=review_path,
                review_execution_path=self._write_review_execution(mapping_available=True),
                output_path=self.root / "results" / "matched-effect.json",
            )

    def test_incomplete_execution_freezes_effect_instead_of_scoring_partial_data(self) -> None:
        report_path = self.root / "results" / "score-report.json"
        payload = json.loads(report_path.read_text(encoding="utf-8"))
        payload["scores"][0]["status"] = "incomplete"
        report_path.write_text(json.dumps(payload), encoding="utf-8")
        with self.assertRaisesRegex(matched_effect.MatchedEffectError, "incomplete"):
            matched_effect.prepare_blind_package(self.root, self.root / "blind-review", seed="fixed-seed")


if __name__ == "__main__":
    unittest.main()
