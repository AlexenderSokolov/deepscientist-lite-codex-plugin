from __future__ import annotations

import copy
import unittest

from teaching import acceptance_gate


class AcceptanceGateTests(unittest.TestCase):
    def gate(self) -> dict:
        return acceptance_gate.start_gate(
            gate_id="canary-01",
            input_refs=["canary/PROMPT.md"],
            authorization_ref="authorizations/canary.md",
            expected_observations=["thread.started", "turn.completed", "final.feedback"],
        )

    def test_start_gate_requires_project_relative_authorization(self) -> None:
        with self.assertRaises(acceptance_gate.GateError):
            acceptance_gate.start_gate(
                gate_id="canary-01",
                input_refs=["canary/PROMPT.md"],
                authorization_ref="",
                expected_observations=["thread.started"],
            )

    def test_execution_gate_requires_terminal_turn_feedback_and_usage(self) -> None:
        record = self.gate()
        for observation in ("thread.started", "tool.observed"):
            acceptance_gate.record_observation(record, observation)
        result = acceptance_gate.finalize_gate(
            record,
            status="blocked",
            failure_category="observation",
            next_action="stop before the next gate",
        )
        self.assertEqual(result["status"], "blocked")
        self.assertFalse(acceptance_gate.can_enter_next_gate(result))

    def test_completed_gate_requires_final_feedback_and_nonzero_usage(self) -> None:
        record = self.gate()
        for observation in ("thread.started", "turn.completed", "final.feedback"):
            acceptance_gate.record_observation(record, observation)
        with self.assertRaisesRegex(acceptance_gate.GateError, "usage"):
            acceptance_gate.finalize_gate(
                record,
                status="passed",
                failure_category="none",
                next_action="continue",
            )
        record["usage"] = {"total_tokens": 12}
        result = acceptance_gate.finalize_gate(
            record,
            status="passed",
            failure_category="none",
            next_action="continue",
        )
        self.assertTrue(acceptance_gate.can_enter_next_gate(result))

    def test_cross_check_rejects_revision_mismatch(self) -> None:
        record = self.gate()
        record["graph_revision"] = 4
        with self.assertRaisesRegex(acceptance_gate.GateError, "revision"):
            acceptance_gate.cross_check_artifacts(
                record,
                evidence_refs=["results/canary.json"],
                graph_revision=5,
                status_revision=5,
            )

    def test_sensitive_absolute_and_raw_fields_are_rejected(self) -> None:
        record = self.gate()
        record["evidence_refs"] = ["C:/secrets/result.json"]
        with self.assertRaises(acceptance_gate.GateError):
            acceptance_gate.validate_audit_record(record)
        record = self.gate()
        record["extensions"] = {"raw_jsonl": "events.jsonl"}
        with self.assertRaises(acceptance_gate.GateError):
            acceptance_gate.validate_audit_record(record)

    def test_unknown_fields_are_rejected_but_extensions_are_allowed(self) -> None:
        record = self.gate()
        record["extensions"] = {"example.org/host": "isolated"}
        self.assertEqual(acceptance_gate.validate_audit_record(record), record)
        unknown = copy.deepcopy(record)
        unknown["hidden_reasoning"] = "must not persist"
        with self.assertRaises(acceptance_gate.GateError):
            acceptance_gate.validate_audit_record(unknown)

    def test_ambiguous_or_blocked_gate_cannot_be_promoted(self) -> None:
        for status in ("blocked", "ambiguous", "not-verified"):
            record = self.gate()
            result = acceptance_gate.finalize_gate(
                record,
                status=status,
                failure_category="transport" if status == "ambiguous" else "observation",
                next_action="create a fresh pilot id",
            )
            self.assertFalse(acceptance_gate.can_enter_next_gate(result))


if __name__ == "__main__":
    unittest.main()
