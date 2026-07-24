from __future__ import annotations

import unittest

from teaching import transport_diagnostics


class TransportDiagnosticTests(unittest.TestCase):
    def finalize(self, stderr: str = "", **overrides: object) -> dict:
        reducer = transport_diagnostics.TransportDiagnosticReducer()
        if stderr:
            reducer.consume(stderr)
        observations = {
            "exit_code": 1,
            "timed_out": False,
            "turn_completed": False,
            "turn_failed": False,
            "child_process_state": "exited",
            "stdout_pipe_state": "closed",
            "stderr_pipe_state": "closed",
        }
        observations.update(overrides)
        return reducer.finalize(**observations)

    def test_auth_response_is_reduced_without_retaining_stderr(self) -> None:
        result = self.finalize(
            "HTTP 401 provider error code=invalid_api_key "
            "token=FAKE-STDERR-SECRET response headers received\n"
        )

        self.assertEqual(result["schema_version"], "ds-lite.transport-diagnostic.v1")
        self.assertEqual(result["category"], "authentication")
        self.assertEqual(result["failure_class"], "auth")
        self.assertEqual(result["http_status_category"], "4xx")
        self.assertEqual(result["provider_error_code"], "invalid_api_key")
        self.assertEqual(result["connection_state"], "established")
        self.assertEqual(result["response_header_state"], "received")
        self.assertEqual(result["subprocess_exit_cause"], "nonzero-exit")
        self.assertNotIn("FAKE-STDERR-SECRET", str(result))

    def test_rate_limit_and_protocol_codes_are_allowlisted(self) -> None:
        cases = (
            ("HTTP 429 code=rate_limit_exceeded response headers received\n", "rate-limit", "rate_limit_exceeded"),
            ("HTTP 200 code=invalid_response malformed response headers received\n", "protocol", "invalid_response"),
            ("HTTP 503 code=vendor_private_code response headers received\n", "protocol", "unrecognized"),
        )
        for stderr, expected_class, expected_code in cases:
            with self.subTest(stderr=stderr):
                result = self.finalize(stderr)
                self.assertEqual(result["failure_class"], expected_class)
                self.assertEqual(result["provider_error_code"], expected_code)

    def test_json_provider_code_is_detected_without_storing_json(self) -> None:
        result = self.finalize('HTTP 401 {"error":{"code":"invalid_api_key","message":"FAKE-STDERR-SECRET"}}\n')
        self.assertEqual(result["provider_error_code"], "invalid_api_key")
        self.assertNotIn("FAKE-STDERR-SECRET", str(result))

    def test_provider_4xx_without_specific_code_is_protocol_not_child_process(self) -> None:
        result = self.finalize(
            'HTTP 400 {"type":"response.failed","response":{"status":"failed","error":{"message":"FAKE-STDERR-SECRET"}}}\n'
        )
        self.assertEqual(result["failure_class"], "protocol")
        self.assertEqual(result["http_status_category"], "4xx")
        self.assertEqual(result["subprocess_exit_cause"], "nonzero-exit")
        self.assertNotIn("FAKE-STDERR-SECRET", str(result))

    def test_network_failure_does_not_invent_response_headers(self) -> None:
        result = self.finalize("connection refused before response header FAKE-STDERR-SECRET\n")
        self.assertEqual(result["failure_class"], "network")
        self.assertEqual(result["connection_state"], "failed")
        self.assertEqual(result["response_header_state"], "not-received")
        self.assertEqual(result["http_status_category"], "none")

    def test_timeout_uses_direct_process_observations(self) -> None:
        result = self.finalize(
            exit_code=-1,
            timed_out=True,
            child_process_state="terminated",
        )
        self.assertEqual(result["failure_class"], "timeout")
        self.assertEqual(result["subprocess_exit_cause"], "timeout")
        self.assertEqual(result["child_process_state"], "terminated")
        self.assertEqual(result["connection_state"], "unknown")

    def test_zero_exit_without_terminal_event_is_ambiguous(self) -> None:
        result = self.finalize(exit_code=0)
        self.assertEqual(result["failure_class"], "ambiguous")
        self.assertEqual(result["subprocess_exit_cause"], "zero-without-terminal")


if __name__ == "__main__":
    unittest.main()
