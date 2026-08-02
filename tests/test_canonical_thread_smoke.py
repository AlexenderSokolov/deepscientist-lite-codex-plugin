import unittest
import subprocess
import sys
from pathlib import Path

from teaching.canonical_thread_smoke import _response_observation, app_server_command, rpc_contract, schema_contract


ROOT = Path(__file__).resolve().parents[1]


class CanonicalThreadSmokeTests(unittest.TestCase):
    def test_launch_command_uses_default_stdio_transport(self):
        codex = Path("C:/codex.cmd")
        self.assertEqual(app_server_command(codex), ["cmd.exe", "/d", "/s", "/c", f'"{codex}" app-server'])

    def test_schema_contract_uses_generated_params_without_guessed_fields(self):
        root = ROOT / "plugins" / "deepscientist-lite-core" / "schemas" / "codex" / "0.128.0"
        contract = schema_contract(root)
        self.assertEqual(contract["ThreadResumeParams"]["required"], ["threadId"])
        self.assertEqual(contract["ThreadReadParams"]["required"], ["threadId"])
        self.assertEqual(contract["ThreadArchiveParams"]["required"], ["threadId"])
        self.assertEqual(contract["ThreadUnarchiveParams"]["required"], ["threadId"])
        self.assertIn("ephemeral", contract["ThreadStartParams"]["properties"])
        self.assertIn("limit", contract["ThreadListParams"]["properties"])

    def test_rpc_contract_is_bound_to_actual_method_names(self):
        root = ROOT / "plugins" / "deepscientist-lite-core" / "schemas" / "codex" / "0.128.0"
        contract = rpc_contract(root)

        self.assertEqual(contract["thread/resume"]["required"], ["threadId"])
        self.assertEqual(contract["thread/read"]["required"], ["threadId"])
        self.assertIn("ephemeral", contract["thread/start"]["properties"])

    def test_script_entrypoint_can_load_package_import(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "teaching" / "canonical_thread_smoke.py"), "--help"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_list_and_read_require_exact_canonical_thread(self):
        listed = {"id": 1, "result": {"data": [{"id": "thread-1"}]}}
        missing = {"id": 1, "result": {"data": [{"id": "thread-other"}]}}
        read = {"id": 2, "result": {"thread": {"id": "thread-1"}}}
        self.assertEqual(_response_observation("thread/list", listed, "thread-1")[0], "observed")
        self.assertEqual(_response_observation("thread/list", missing, "thread-1")[0], "identity-gap")
        self.assertEqual(_response_observation("thread/read", read, "thread-1")[0], "observed")

    def test_json_rpc_error_is_redacted_to_code_and_hash(self):
        status, diagnostic = _response_observation(
            "thread/archive",
            {"id": 3, "error": {"code": -32000, "message": "sensitive host detail", "data": {"kind": "x"}}},
            "thread-1",
        )
        self.assertEqual(status, "response-gap")
        self.assertEqual(diagnostic["error_code"], -32000)
        self.assertNotIn("sensitive host detail", str(diagnostic))


if __name__ == "__main__":
    unittest.main()
