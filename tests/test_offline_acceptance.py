from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from teaching import offline_acceptance


class OfflineAcceptanceTests(unittest.TestCase):
    def test_protocol_status_fails_closed_on_any_false_check(self) -> None:
        self.assertEqual(offline_acceptance.protocol_status(True, True), "passed")
        self.assertEqual(offline_acceptance.protocol_status(True, False), "blocked")

    def test_cross_platform_offline_entrypoints_are_wired_into_validation(self) -> None:
        root = Path(__file__).resolve().parents[1]
        shell = (root / "teaching" / "run_transport_diagnostics.sh").read_text(encoding="utf-8")
        powershell = (root / "teaching" / "run_transport_diagnostics.ps1").read_text(encoding="utf-8")
        validator = (root / "tools" / "validation" / "validate_all.py").read_text(encoding="utf-8")
        for text in (shell, powershell):
            self.assertIn("offline_acceptance.py", text)
            self.assertIn("Output", text.replace("OUTPUT", "Output"))
            self.assertNotIn("communication-beta2-20260720-gated-02", text)
        self.assertIn('root / "teaching"', validator)
        self.assertIn('root / "tests"', validator)

    def test_transport_suite_covers_seven_single_attempt_scenarios(self) -> None:
        parent = Path(tempfile.mkdtemp(prefix="ds-lite-offline-acceptance-"))
        output = parent / "fresh-report"
        report = offline_acceptance.run_offline_acceptance(output)

        self.assertEqual(report["schema_version"], "ds-lite.offline-protocol-acceptance.v1")
        self.assertEqual(report["claim_scope"], "fake-provider-and-fake-codex-only")
        self.assertEqual(report["overall_status"], "passed")
        self.assertEqual(report["status"], report["overall_status"])
        self.assertFalse(report["real_provider_verified"])
        self.assertFalse(report["real_gates_unlocked"])
        rows = {row["scenario"]: row for row in report["transport"]["scenarios"]}
        self.assertEqual(
            set(rows),
            {"success", "auth-failure", "rate-limit", "network-failure", "malformed-response", "child-early-exit", "ambiguous-transport"},
        )
        self.assertEqual(rows["success"]["status"], "completed")
        self.assertEqual(rows["auth-failure"]["failure_class"], "auth")
        self.assertEqual(rows["rate-limit"]["failure_class"], "rate-limit")
        self.assertEqual(rows["network-failure"]["failure_class"], "network")
        self.assertEqual(rows["malformed-response"]["failure_class"], "protocol")
        self.assertEqual(rows["child-early-exit"]["failure_class"], "child-process")
        self.assertEqual(rows["ambiguous-transport"]["failure_class"], "ambiguous")
        for scenario, row in rows.items():
            self.assertEqual(row["fake_codex_launch_count"], 1)
            self.assertLessEqual(row["provider_request_count"], 1)
            self.assertFalse(row["automatic_retry_observed"])
            self.assertFalse(row["raw_stderr_persisted"])
            self.assertIn("provider_response_facts", row)
            self.assertIn("response_event_shape", row)
            self.assertNotIn("FAKE-RESPONSE-SECRET", json.dumps(row))
            if scenario == "child-early-exit":
                self.assertEqual(row["provider_request_count"], 0)
            else:
                self.assertEqual(row["provider_request_count"], 1)

        self.assertEqual(rows["auth-failure"]["provider_response_facts"]["http_status"], 401)
        self.assertEqual(rows["auth-failure"]["provider_response_facts"]["error_type"], "authentication_error")
        self.assertEqual(rows["auth-failure"]["provider_response_facts"]["error_code"], "invalid_api_key")
        self.assertEqual(rows["rate-limit"]["provider_response_facts"]["http_status"], 429)
        self.assertRegex(rows["success"]["provider_response_facts"]["request_id_sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(rows["success"]["response_event_shape"][-1], "turn.completed")

        saved = (output / "offline-acceptance.json").read_text(encoding="utf-8")
        self.assertEqual(json.loads(saved), report)
        self.assertNotIn("FAKE-STDERR-SECRET", saved)
        self.assertNotIn(str(parent), saved)

        protocols = report["protocols"]
        self.assertEqual(protocols["hook"]["claim"], "fake-host-tested")
        self.assertEqual(protocols["hook"]["host_loading"], "real-host-not-verified")
        self.assertTrue(protocols["hook"]["redacted_context"])
        self.assertTrue(protocols["hook"]["dangerous_write_blocked"])
        self.assertTrue(protocols["hook"]["read_only_allowed"])
        self.assertTrue(protocols["hook"]["stop_reentry_guarded"])

        self.assertEqual(protocols["delegation"]["claim"], "protocol-tested")
        self.assertEqual(protocols["delegation"]["host_dispatch"], "host-dispatch-not-verified")
        self.assertTrue(protocols["delegation"]["plan_only_stopped"])
        self.assertTrue(protocols["delegation"]["overlap_rejected"])
        self.assertTrue(protocols["delegation"]["parent_integration_verified"])

        self.assertEqual(protocols["matched_comparison"]["claim"], "prepared-and-freeze-tested")
        self.assertEqual(protocols["matched_comparison"]["effect"], "effect-not-measured")
        self.assertEqual(protocols["matched_comparison"]["run_count"], 12)
        self.assertTrue(protocols["matched_comparison"]["equal_input_digests"])
        self.assertTrue(protocols["matched_comparison"]["failed_execution_frozen"])
        self.assertEqual(protocols["matched_comparison"]["score_status"], "incomplete")

    def test_offline_report_refuses_existing_output(self) -> None:
        parent = Path(tempfile.mkdtemp(prefix="ds-lite-offline-existing-"))
        output = parent / "existing"
        output.mkdir()
        with self.assertRaisesRegex(offline_acceptance.OfflineAcceptanceError, "already exists"):
            offline_acceptance.run_offline_acceptance(output)


if __name__ == "__main__":
    unittest.main()
