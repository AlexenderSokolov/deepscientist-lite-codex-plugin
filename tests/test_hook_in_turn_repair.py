import hashlib
import unittest
from pathlib import Path

from teaching.hook_in_turn_repair_acceptance import evaluate_observation


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_ROOT = ROOT / "plugins" / "deepscientist-lite-core" / "schemas" / "codex" / "0.128.0"


class HookInTurnRepairTests(unittest.TestCase):
    def test_missing_real_host_observation_fails_closed(self):
        result = evaluate_observation({}, schema_digest="schema-digest")
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["failure_layer"], "real-host-not-observed")

    def test_only_one_controller_turn_and_two_stop_events_are_required(self):
        observation = {
            "evidence_class": "real-host",
            "schema_digest": "schema-digest",
            "controller_turn_start_count": 1,
            "stop_events": [
                {"turn_id": "turn-1", "decision": "block", "reason": "repair required", "stop_hook_active": False},
                {"turn_id": "turn-1", "decision": "allow", "reason": "handoff after budget", "stop_hook_active": True},
            ],
            "terminal": {"kind": "hook_handoff", "turn_id": "turn-1"},
        }
        result = evaluate_observation(observation, schema_digest="schema-digest")
        self.assertEqual(result["status"], "passed")
        self.assertTrue(result["deterministic_verifier"])

    def test_second_turn_or_missing_reason_is_rejected(self):
        observation = {
            "evidence_class": "real-host",
            "schema_digest": "schema-digest",
            "controller_turn_start_count": 2,
            "stop_events": [
                {"turn_id": "turn-1", "decision": "block", "reason": "repair required", "stop_hook_active": False},
                {"turn_id": "turn-1", "decision": "allow", "reason": "", "stop_hook_active": True},
            ],
            "terminal": {"kind": "hook_handoff", "turn_id": "turn-1"},
        }
        result = evaluate_observation(observation, schema_digest="schema-digest")
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["failure_layer"], "controller-turn-count")

    def test_generated_schema_pin_is_complete_and_identifies_required_rpc_files(self):
        sums = (SCHEMA_ROOT / "SHA256SUMS").read_text(encoding="utf-8").splitlines()
        expected = {}
        for line in sums:
            relative, digest = line.rsplit(":", 1)
            relative = relative.replace("\\", "/")
            expected[relative] = digest
        self.assertIn("v2/ThreadStartParams.json", expected)
        self.assertIn("v2/ThreadResumeParams.json", expected)
        self.assertIn("v2/ThreadListParams.json", expected)
        self.assertIn("v2/ThreadReadParams.json", expected)
        self.assertIn("v2/ThreadArchiveParams.json", expected)
        self.assertIn("v2/ThreadUnarchiveParams.json", expected)
        for relative, digest in expected.items():
            self.assertEqual(hashlib.sha256((SCHEMA_ROOT / relative).read_bytes()).hexdigest().upper(), digest)


if __name__ == "__main__":
    unittest.main()
