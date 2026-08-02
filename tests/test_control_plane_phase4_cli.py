from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTROLLER_ROOT = ROOT / "plugins" / "deepscientist-lite-core" / "controller"
sys.path.insert(0, str(CONTROLLER_ROOT))

from ds_lite_control.cli import build_parser, main


class Phase4CliTests(unittest.TestCase):
    def test_phase4_managed_commands_are_stable(self) -> None:
        parser = build_parser()
        evidence = parser.parse_args([
            "control", "evidence", "freeze", "job-1", "gate-a",
            "--project", ".", "--artifact-root", ".", "--policy", "policy.json",
        ])
        self.assertEqual(evidence.control_command, "evidence")
        verify = parser.parse_args([
            "control", "verify", "job-1", "gate-a", "--project", ".",
            "--evidence-set", "evidence-1", "--policy", "policy.json",
        ])
        self.assertEqual(verify.control_command, "verify")
        review = parser.parse_args([
            "control", "review", "job-1", "gate-a", "--project", ".",
            "--evidence-set", "evidence-1", "--broker-endpoint", "127.0.0.1:1",
            "--broker-token-file", "token.json", "--schema-root", ".",
        ])
        self.assertEqual(review.control_command, "review")
        aggregate = parser.parse_args([
            "control", "aggregate", "job-1", "--project", ".", "--profile", "profile.json",
        ])
        self.assertEqual(aggregate.control_command, "aggregate")

    def test_evidence_and_verify_commands_emit_write_once_receipts(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ds-lite-phase4-cli-") as directory:
            root = Path(directory)
            artifacts = root / "artifacts"
            artifacts.mkdir()
            (artifacts / "result.json").write_text(
                json.dumps({"schema_version": "fixture.result.v1", "measurement": 42}),
                encoding="utf-8",
            )
            policy = root / "policy.json"
            policy.write_text(json.dumps({
                "schema_version": "ds-lite.gate-policy.v1",
                "policy_id": "policy-v1", "minimum_evidence_class": "offline",
                "required_artifacts": [{
                    "path": "result.json", "schema_version": "fixture.result.v1",
                    "required_fields": {"measurement": 42},
                }],
            }), encoding="utf-8")
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = main([
                    "control", "evidence", "freeze", "job-1", "gate-a",
                    "--project", str(root), "--artifact-root", str(artifacts),
                    "--policy", str(policy), "--owner-id", "owner-1",
                ])
            self.assertEqual(code, 0)
            manifest = json.loads(output.getvalue())
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = main([
                    "control", "verify", "job-1", "gate-a", "--project", str(root),
                    "--evidence-set", manifest["evidence_set_id"], "--policy", str(policy),
                    "--owner-id", "owner-1",
                ])
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(output.getvalue())["status"], "passed")

            profile = root / "profile.json"
            profile.write_text(json.dumps({
                "schema_version": "ds-lite.release-profile.v1",
                "profile_id": "phase5-readiness",
                "required_gates": ["gate-a", "phase5-host"],
                "fixture_only": False,
            }), encoding="utf-8")
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = main([
                    "control", "aggregate", "job-1", "--project", str(root),
                    "--profile", str(profile), "--owner-id", "release-owner",
                ])
            decision = json.loads(output.getvalue())
            self.assertEqual(code, 2)
            self.assertFalse(decision["release_allowed"])
            self.assertTrue((root / ".ds-lite" / "receipts" /
                             f"{decision['receipt_id']}.json").is_file())


if __name__ == "__main__":
    unittest.main()
