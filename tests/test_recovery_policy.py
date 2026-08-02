import unittest

from plugins.deepscientist_lite_import_shim import ds_lite_recovery


class RecoveryPolicyTests(unittest.TestCase):
    def test_http_policy_matrix(self):
        expected = {
            401: "awaiting-user-action", 402: "awaiting-user-action", 403: "awaiting-user-action",
            408: "retryable", 429: "retryable", 500: "retryable", 502: "retryable",
            503: "retryable", 504: "retryable", 400: "terminal", 422: "terminal",
        }
        for status, recovery_class in expected.items():
            with self.subTest(status=status):
                self.assertEqual(ds_lite_recovery.classify_failure("provider", http_status=status)["recovery_class"], recovery_class)

    def test_transport_session_and_unknown_policy_matrix(self):
        self.assertEqual(ds_lite_recovery.classify_failure("network")["recovery_class"], "retryable")
        self.assertEqual(ds_lite_recovery.classify_failure("connection-reset")["recovery_class"], "retryable")
        self.assertEqual(ds_lite_recovery.classify_failure("session-drift")["recovery_class"], "terminal")
        self.assertEqual(ds_lite_recovery.classify_failure("unrecognized-upstream")["recovery_class"], "diagnose-once")

    def test_retry_after_is_bounded_and_redacted(self):
        schedule = ds_lite_recovery.retry_schedule(3, retry_after_seconds=9)
        self.assertEqual(schedule["retry_after_seconds"], 9)
        self.assertEqual(schedule["retry_delay_seconds"], 9)
        self.assertIn("T", schedule["next_retry_at"])


if __name__ == "__main__":
    unittest.main()
