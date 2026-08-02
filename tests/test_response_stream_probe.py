import unittest

from teaching.response_stream_probe import _event_name, probe


class ResponseStreamProbeTests(unittest.TestCase):
    def test_extracts_only_sse_event_names(self):
        self.assertEqual(_event_name(b"event: response.completed\n"), "response.completed")
        self.assertIsNone(_event_name(b"data: confidential provider output\n"))
        self.assertIsNone(_event_name(b"\n"))

    def test_direct_egress_is_reported_without_provider_content(self):
        result = probe("https://127.0.0.1:1/v1", "test-model", "test-key", 1, direct_egress=True)
        self.assertTrue(result["direct_egress_requested"])
        self.assertFalse(result["raw_provider_content_persisted"])


if __name__ == "__main__":
    unittest.main()
