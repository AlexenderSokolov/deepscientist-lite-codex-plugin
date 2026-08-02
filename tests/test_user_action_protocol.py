from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "plugins" / "deepscientist-lite-core" / "scripts"))
import ds_lite_hook  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "plugins" / "deepscientist-lite-core"
ACTION = CORE / "scripts" / "ds_lite_user_action.py"
HOOK = CORE / "scripts" / "ds_lite_hook.py"


class UserActionProtocolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="ds-lite-user-action-"))
        (self.root / "PROJECT.md").write_text("# test\n", encoding="utf-8")
        (self.root / "research" / "state").mkdir(parents=True)
        (self.root / "research" / "work-unit.json").write_text("{}\n", encoding="utf-8")
        (self.root / "research" / "state" / "graph.json").write_text("{}\n", encoding="utf-8")

    def run_action(self, *args: str) -> dict[str, object]:
        result = subprocess.run([sys.executable, str(ACTION), *args], cwd=ROOT, text=True, encoding="utf-8", capture_output=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return json.loads(result.stdout)

    def run_hook(self, event: str, payload: dict[str, object]) -> dict[str, object]:
        # The CLI intentionally emits the strict Codex host envelope. Exercise
        # the richer internal decision object directly to avoid executing the
        # side-effecting request gate twice in one test.
        return ds_lite_hook.handle_event(event, payload)

    def test_browser_action_creates_request_and_blocks(self) -> None:
        payload = self.run_hook("pre-tool-use", {"cwd": str(self.root), "tool_name": "Bash", "command": "playwright open https://example.com"})
        self.assertEqual(payload["decision"], "block")
        self.assertEqual(payload["failure_category"], "user-action/required")
        requests = list((self.root / "research" / "artifacts").glob("user-action-request-*.json"))
        self.assertEqual(len(requests), 1)
        text = requests[0].read_text(encoding="utf-8")
        self.assertNotIn(str(self.root), text)
        self.assertNotIn("prompt", text.lower())

    def test_app_server_provider_session_has_a_distinct_authorization_scope(self) -> None:
        payload = self.run_hook(
            "pre-tool-use",
            {"cwd": str(self.root), "tool_name": "Bash", "command": "codex app-server --stdio"},
        )
        self.assertEqual(payload["decision"], "block")
        self.assertIn("provider-session", payload["reason"])
        request = next((self.root / "research" / "artifacts").glob("user-action-request-*.json"))
        saved = json.loads(request.read_text(encoding="utf-8"))
        self.assertEqual(saved["extensions"]["scope"], "provider-session")
        self.assertNotIn(str(self.root), json.dumps(saved, ensure_ascii=False))

    def test_matching_response_unlocks_once(self) -> None:
        first = self.run_hook("pre-tool-use", {"cwd": str(self.root), "tool_name": "Bash", "command": "curl https://example.com"})
        request_id = first["reason"].split("user-action-request-")[-1].split(".json")[0]
        self.run_action("respond", "--root", str(self.root), "--request-id", request_id, "--decision", "allow", "--scope", "web-provider", "--receipt-ref", "research/artifacts/web-provider-acceptance.json")
        unlocked = self.run_hook("pre-tool-use", {"cwd": str(self.root), "tool_name": "Bash", "command": "curl https://example.com"})
        self.assertEqual(unlocked["decision"], "allow")
        self.assertEqual(unlocked["user_action"]["status"], "consumed")
        repeated = self.run_hook("pre-tool-use", {"cwd": str(self.root), "tool_name": "Bash", "command": "curl https://example.com"})
        self.assertEqual(repeated["decision"], "block")

    def test_consume_cli_preserves_the_response_schema(self) -> None:
        first = self.run_hook("pre-tool-use", {"cwd": str(self.root), "tool_name": "Bash", "command": "curl https://example.com"})
        request_id = first["reason"].split("user-action-request-")[-1].split(".json")[0]
        self.run_action("respond", "--root", str(self.root), "--request-id", request_id, "--decision", "allow", "--scope", "web-provider", "--receipt-ref", "research/artifacts/web-provider-acceptance.json")
        consumed = self.run_action("consume", "--root", str(self.root), "--request-id", request_id)
        self.assertEqual(consumed["status"], "consumed")
        self.assertIn("consumed_at", consumed["extensions"])

    def test_denied_response_does_not_unlock(self) -> None:
        first = self.run_hook("pre-tool-use", {"cwd": str(self.root), "tool_name": "Bash", "command": "tmux new-session -d"})
        request_id = first["reason"].split("user-action-request-")[-1].split(".json")[0]
        self.run_action("respond", "--root", str(self.root), "--request-id", request_id, "--decision", "deny", "--scope", "long-task", "--receipt-ref", "research/artifacts/long-task-acceptance.json")
        denied = self.run_hook("pre-tool-use", {"cwd": str(self.root), "tool_name": "Bash", "command": "tmux new-session -d"})
        self.assertEqual(denied["decision"], "block")

    def test_agent_resolution_clears_an_obsolete_request_without_faking_user_response(self) -> None:
        first = self.run_hook("pre-tool-use", {"cwd": str(self.root), "tool_name": "Bash", "command": "curl https://example.com"})
        request_id = first["reason"].split("user-action-request-")[-1].split(".json")[0]
        resolution = self.run_action(
            "resolve", "--root", str(self.root), "--request-id", request_id,
            "--reason", "network route recovered", "--verification", "public metadata query returned a repository head",
        )
        self.assertEqual(resolution["schema_version"], "ds-lite.agent-action-resolution.v1")
        self.assertEqual(resolution["status"], "resolved")
        self.assertFalse((self.root / "research" / "artifacts" / f"user-action-response-{request_id}.json").exists())
        prompt = self.run_hook("user-prompt-submit", {"cwd": str(self.root)})
        self.assertNotIn("user_action_request", prompt)

    def test_prompt_and_stop_expose_unresolved_request(self) -> None:
        self.run_hook("pre-tool-use", {"cwd": str(self.root), "tool_name": "Bash", "command": "python delegate child"})
        prompt = self.run_hook("user-prompt-submit", {"cwd": str(self.root)})
        self.assertIn("user_action_request", prompt)
        stop = self.run_hook("stop", {"cwd": str(self.root)})
        self.assertEqual(stop["decision"], "block")
        self.assertIn("user action request", stop["additional_context"])


if __name__ == "__main__":
    unittest.main()
