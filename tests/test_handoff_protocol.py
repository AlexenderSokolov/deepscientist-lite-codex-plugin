from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from teaching import handoff_protocol


class HandoffProtocolTests(unittest.TestCase):
    def payload(self):
        return handoff_protocol.build_handoff(
            handoff_id="handoff-01",
            kind="conversation",
            status="ready",
            goal="verify one bounded CLI boundary",
            observed_facts=["preflight passed"],
            hypotheses=["the child process may close a pipe late"],
            authorization_boundary=["one fresh diagnostic request", "no retry"],
            configuration={"cli_version": "0.144.5", "model": "gpt-5.6-sol", "retry_policy": "zero"},
            evidence_refs=["results/preflight.json"],
            failure_layer="none",
            unverified=["fresh host"],
            next_action="run one fresh process probe",
        )

    def test_digest_and_redacted_configuration_are_required(self):
        payload = self.payload()
        self.assertEqual(len(payload["context_digest"]), 64)
        self.assertEqual(handoff_protocol.validate_handoff(payload), payload)
        payload["configuration"]["api_key"] = "secret"
        with self.assertRaises(handoff_protocol.HandoffError):
            handoff_protocol.validate_handoff(payload)

    def test_absolute_refs_and_raw_prompt_are_rejected(self):
        payload = self.payload()
        payload["evidence_refs"] = ["C:/secret.json"]
        with self.assertRaises(handoff_protocol.HandoffError):
            handoff_protocol.validate_handoff(payload)
        payload = self.payload()
        payload["extensions"] = {"prompt": "do not persist"}
        with self.assertRaises(handoff_protocol.HandoffError):
            handoff_protocol.validate_handoff(payload)

    def test_handoff_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "handoff.json"
            handoff_protocol.write_fresh_handoff(path, self.payload())
            with self.assertRaises(handoff_protocol.HandoffError):
                handoff_protocol.write_fresh_handoff(path, self.payload())

    def test_optional_host_mapping_keeps_schema_and_lifecycle_ownership_separate(self):
        payload = self.payload()
        payload["extensions"] = {
            "host_mapping": {
                "schema_version": "ds-lite.host-mapping.v1",
                "coordinator_host_id": "openscience.task-42",
                "worker_host_ids": {
                    "task-a": "codex.task-a",
                    "task-b": "tmux.pane-2",
                },
            }
        }
        self.assertEqual(handoff_protocol.validate_handoff(payload), payload)
        payload["extensions"]["host_mapping"]["worker_host_ids"]["task-b"] = "codex.task-a"
        with self.assertRaisesRegex(handoff_protocol.HandoffError, "unique"):
            handoff_protocol.validate_handoff(payload)

    def test_installed_core_has_a_standalone_handoff_validator(self):
        script = (
            Path(__file__).resolve().parents[1]
            / "plugins"
            / "deepscientist-lite-core"
            / "scripts"
            / "ds_lite_handoff.py"
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "handoff.json"
            path.write_text(json.dumps(self.payload()), encoding="utf-8")
            completed = subprocess.run(
                [sys.executable, str(script), "validate", "--path", str(path)],
                text=True,
                encoding="utf-8",
                capture_output=True,
            )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertEqual(json.loads(completed.stdout)["status"], "passed")


if __name__ == "__main__":
    unittest.main()
