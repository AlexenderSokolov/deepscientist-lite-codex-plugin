from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from teaching import fresh_host_probe


class FreshHostProbeTests(unittest.TestCase):
    def _fake(self, root: Path, body: str) -> Path:
        path = root / "fake.py"
        path.write_text(body, encoding="utf-8")
        return path

    def test_success_receipt_is_terminal_and_redacted(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fake = self._fake(root, "import json; print(json.dumps({'type':'thread.started'})); print(json.dumps({'type':'turn.completed'}))")
            receipt = fresh_host_probe.run_once(codex_bin=fake, codex_home=root, workspace=root, prompt="secret prompt", output_path=root / "result.json")
            self.assertEqual(receipt["status"], "test-only-passed")
            self.assertEqual(receipt["cli_task_status"], "passed")
            self.assertTrue(receipt["terminal_event_observed"])
            self.assertFalse(receipt["raw_output_persisted"])
            self.assertIn("Hook host loading", receipt["unverified"])
            self.assertIn("Hook Stop", receipt["unverified"])
            self.assertNotIn("secret prompt", (root / "result.json").read_text(encoding="utf-8"))

    def test_zero_event_process_is_blocked_and_cannot_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fake = self._fake(root, "raise SystemExit(1)")
            output = root / "result.json"
            receipt = fresh_host_probe.run_once(codex_bin=fake, codex_home=root, workspace=root, prompt="p", output_path=output)
            self.assertEqual(receipt["status"], "blocked")
            with self.assertRaises(fresh_host_probe.FreshHostProbeError):
                fresh_host_probe.run_once(codex_bin=fake, codex_home=root, workspace=root, prompt="p", output_path=output)

    def test_model_free_checks_do_not_send_prompt(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fake = self._fake(root, "import sys; print('codex 0.144.5') if sys.argv[1:] == ['--version'] else print('{}')")
            receipt = fresh_host_probe.run_model_free_checks(codex_bin=fake, codex_home=root, workspace=root, output_path=root / "model-free.json")
            self.assertTrue(receipt["no_external_model_request"])
            self.assertFalse(receipt["raw_output_persisted"])
            self.assertEqual(len(receipt["checks"]), 3)
            self.assertIsNone(receipt["checks"][0]["version_observed"])

    def test_exec_probe_uses_pinned_cli_compatible_flags(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fake = self._fake(root, "import sys; print('argv=' + ' '.join(sys.argv[1:])); print('{\\\"type\\\":\\\"turn.completed\\\"}')")
            receipt = fresh_host_probe.run_once(codex_bin=fake, codex_home=root, workspace=root, prompt="p", output_path=root / "result.json")
            self.assertEqual(receipt["status"], "test-only-passed")
            self.assertNotIn("ask-for-approval", (root / "result.json").read_text(encoding="utf-8"))

    def test_hook_event_summary_is_redacted(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            events = root / "events"
            events.mkdir()
            (events / "event.json").write_text('{"event_type":"UserPromptSubmit","decision":"allow","secret":"hidden"}', encoding="utf-8")
            fake = self._fake(root, "import json; print(json.dumps({'type':'turn.completed'}))")
            receipt = fresh_host_probe.run_once(codex_bin=fake, codex_home=root, workspace=root, prompt="p", output_path=root / "result.json", hook_events_path=events)
            self.assertEqual(receipt["hook_events"], [{"event_type": "user-prompt-submit", "decision": "allow"}])
            self.assertNotIn("hidden", (root / "result.json").read_text(encoding="utf-8"))

    def test_unrecognized_cli_and_hook_values_are_counted_but_never_persisted(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            marker = "SECRET-MARKER-IN-ARBITRARY-TYPE"
            events = root / "events"
            events.mkdir()
            (events / "valid.json").write_text(
                json.dumps({"event_type": "PreToolUse", "decision": "block"}), encoding="utf-8"
            )
            (events / "invalid.json").write_text(
                json.dumps({"event_type": marker, "decision": marker}), encoding="utf-8"
            )
            fake = self._fake(
                root,
                "import json\n"
                f"print(json.dumps({{'type': {marker!r}}}))\n"
                "print(json.dumps({'type': 'turn.completed'}))\n",
            )

            receipt = fresh_host_probe.run_once(
                codex_bin=fake,
                codex_home=root,
                workspace=root,
                prompt="p",
                output_path=root / "result.json",
                hook_events_path=events,
            )

            saved = (root / "result.json").read_text(encoding="utf-8")
            self.assertEqual(receipt["event_types"], ["turn.completed"])
            self.assertEqual(receipt["event_type_counts"], {"turn.completed": 1})
            self.assertEqual(receipt["unrecognized_event_count"], 1)
            self.assertEqual(receipt["hook_events"], [{"event_type": "pre-tool-use", "decision": "block"}])
            self.assertEqual(receipt["unrecognized_hook_event_count"], 1)
            self.assertNotIn(marker, saved)

    def test_expected_cli_identity_is_pairwise_and_hash_enforced_before_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            marker = root / "executed.txt"
            fake = self._fake(
                root,
                "import json\n"
                "from pathlib import Path\n"
                f"Path({str(marker)!r}).write_text('ran')\n"
                "print(json.dumps({'type': 'turn.completed'}))\n",
            )
            output = root / "result.json"

            with self.assertRaisesRegex(fresh_host_probe.FreshHostProbeError, "together"):
                fresh_host_probe.run_once(
                    codex_bin=fake,
                    codex_home=root,
                    workspace=root,
                    prompt="p",
                    output_path=output,
                    expected_cli_version="0.144.5",
                )
            with self.assertRaisesRegex(fresh_host_probe.FreshHostProbeError, "SHA-256"):
                fresh_host_probe.run_once(
                    codex_bin=fake,
                    codex_home=root,
                    workspace=root,
                    prompt="p",
                    output_path=output,
                    expected_cli_version="0.144.5",
                    expected_cli_sha256="0" * 64,
                )
            self.assertFalse(marker.exists())
            self.assertFalse(output.exists())

            actual_hash = hashlib.sha256(fake.read_bytes()).hexdigest()
            receipt = fresh_host_probe.run_once(
                codex_bin=fake,
                codex_home=root,
                workspace=root,
                prompt="p",
                output_path=output,
                expected_cli_version="0.144.5",
                expected_cli_sha256=actual_hash,
            )
            self.assertTrue(receipt["cli_identity"]["enforced"])
            self.assertTrue(receipt["cli_identity"]["sha256_match"])
            self.assertEqual(receipt["status"], "passed")
            self.assertEqual(receipt["cli_task_status"], "passed")
            self.assertIn("Hook host loading", receipt["unverified"])
            self.assertIn("Hook UserPromptSubmit", receipt["unverified"])
            self.assertIn("Hook PreToolUse", receipt["unverified"])
            self.assertIn("Hook PostToolUse", receipt["unverified"])
            self.assertIn("Hook Stop", receipt["unverified"])

    def test_model_free_version_is_canonicalized_before_receipt_persistence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            marker = "SECRET-MARKER-AS-VERSION"
            fake = self._fake(
                root,
                "import sys\n"
                f"print('codex-cli {marker}' if sys.argv[1:] == ['--version'] else '{{}}')\n",
            )
            receipt = fresh_host_probe.run_model_free_checks(
                codex_bin=fake,
                codex_home=root,
                workspace=root,
                output_path=root / "model-free.json",
            )
            self.assertEqual(receipt["checks"][0]["version_observed"], "unexpected")
            self.assertNotIn(marker, (root / "model-free.json").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
