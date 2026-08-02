import io
import json
import threading
import unittest

from teaching.app_server_transport import (
    AppServerClosed,
    AppServerProtocolError,
    AppServerResponseTimeout,
    JsonRpcTransport,
    classify_thread_observation,
    validate_params,
)


class FakeProcess:
    def __init__(self, responses):
        self.stdin = io.StringIO()
        self.stdout = io.StringIO("".join(responses))


class BlockingStdout:
    def readline(self):
        threading.Event().wait(5)
        return ""


class BlockingProcess:
    def __init__(self):
        self.stdin = io.StringIO()
        self.stdout = BlockingStdout()


class AppServerTransportTests(unittest.TestCase):
    def test_rejects_unknown_schema_parameter(self):
        with self.assertRaises(AppServerProtocolError):
            validate_params(
                "thread/read",
                {"threadId": "thread-1", "guessed": True},
                {"thread/read": {"required": ["threadId"], "properties": ["threadId", "includeTurns"]}},
            )

    def test_buffers_notification_that_arrives_before_response(self):
        process = FakeProcess([
            json.dumps({"method": "turn/completed", "params": {"threadId": "thread-1"}}) + "\n",
            json.dumps({"id": 1, "result": {"thread": {"id": "thread-1"}}}) + "\n",
        ])
        transport = JsonRpcTransport(process)

        response = transport.request("thread/start", {"cwd": "C:/workspace"})

        self.assertEqual(response["result"]["thread"]["id"], "thread-1")
        self.assertEqual(transport.notifications, [{"method": "turn/completed", "params": {"threadId": "thread-1"}}])

    def test_eof_before_response_is_a_response_gap(self):
        transport = JsonRpcTransport(FakeProcess([]))

        with self.assertRaises(AppServerClosed):
            transport.request("thread/list", {"limit": 1})

    def test_silent_process_has_bounded_response_timeout(self):
        transport = JsonRpcTransport(BlockingProcess(), response_timeout=0.01)
        with self.assertRaises(AppServerResponseTimeout):
            transport.request("thread/list", {"limit": 1})

    def test_malformed_json_is_isolated_before_matching_response(self):
        process = FakeProcess([
            "not-json\n",
            json.dumps({"id": 1, "result": {"data": []}}) + "\n",
        ])
        transport = JsonRpcTransport(process)

        response = transport.request("thread/list", {"limit": 1})

        self.assertEqual(response["result"], {"data": []})
        self.assertEqual(transport.malformed_message_count, 1)

    def test_missing_thread_is_ambiguous_without_start_fallback(self):
        result = classify_thread_observation(thread_id="thread-1", response=None, notifications=[])

        self.assertEqual(result, "ambiguous")

    def test_terminal_notification_classifies_exact_thread_as_terminal(self):
        result = classify_thread_observation(
            thread_id="thread-1",
            response=None,
            notifications=[{"method": "turn/completed", "params": {"threadId": "thread-1"}}],
        )

        self.assertEqual(result, "terminal")


if __name__ == "__main__":
    unittest.main()
