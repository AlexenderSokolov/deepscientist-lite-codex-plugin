from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from teaching import aggregate_trusted_hook_acceptance as aggregation


def host(events: list[tuple[str, str]]) -> dict:
    return {
        "status": "passed", "failure_layer": "none", "automatic_retry_observed": False,
        "raw_output_persisted": False,
        "cli_identity": {"expected_version": "0.144.5"},
        "hook_events": [{"event_type": event, "decision": decision} for event, decision in events],
    }


class AggregateTrustedHookAcceptanceTests(unittest.TestCase):
    def test_combines_two_fresh_hosts_without_claiming_agent_closure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            a = root / "a.json"; b = root / "b.json"; fixture = root / "fixture.json"
            a.write_text(json.dumps(host([("user-prompt-submit", "allow"), ("pre-tool-use", "block"),
                                          ("post-tool-use", "allow"), ("stop", "block")])), encoding="utf-8")
            b.write_text(json.dumps(host([("user-prompt-submit", "allow"), ("pre-tool-use", "allow"),
                                          ("post-tool-use", "allow"), ("stop", "allow")])), encoding="utf-8")
            fixture.write_text(json.dumps({"terminal_fixture_prepared": True,
                                           "agent_initiated_terminal_closure": "not-observed"}), encoding="utf-8")
            result = aggregation.aggregate(a, b, fixture)
            self.assertEqual(result["status"], "passed")
            self.assertEqual(result["agent_initiated_terminal_closure"], "not-observed")

    def test_rejects_host_b_without_stop_allow(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            a = root / "a.json"; b = root / "b.json"; fixture = root / "fixture.json"
            a.write_text(json.dumps(host([("user-prompt-submit", "allow"), ("pre-tool-use", "block"),
                                          ("post-tool-use", "allow"), ("stop", "block")])), encoding="utf-8")
            b.write_text(json.dumps(host([("user-prompt-submit", "allow"), ("pre-tool-use", "allow"),
                                          ("post-tool-use", "allow")])), encoding="utf-8")
            fixture.write_text(json.dumps({"terminal_fixture_prepared": True,
                                           "agent_initiated_terminal_closure": "not-observed"}), encoding="utf-8")
            with self.assertRaisesRegex(aggregation.AcceptanceError, "Host B"):
                aggregation.aggregate(a, b, fixture)


if __name__ == "__main__":
    unittest.main()
