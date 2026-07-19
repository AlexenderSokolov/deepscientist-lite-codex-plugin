from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
AUDIT_SCRIPT = REPO_ROOT / "plugins" / "deepscientist-lite" / "scripts" / "ds_lite_communication_audit.py"


class CommunicationAuditTests(unittest.TestCase):
    def setUp(self) -> None:
        self.parent = Path(tempfile.mkdtemp(prefix="ds-lite audit 中文 "))
        self.root = self.parent / "project with spaces 中文"
        self.root.mkdir()

    def run_cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(AUDIT_SCRIPT), *args],
            cwd=REPO_ROOT,
            text=True,
            encoding="utf-8",
            capture_output=True,
        )

    def init(self) -> Path:
        result = self.run_cli(
            "init",
            "--root",
            str(self.root),
            "--skill",
            "ds-lite-experiment",
            "--task-class",
            "repository-change",
            "--profile",
            "research-peer",
            "--detail-mode",
            "adaptive",
            "--id",
            "audit-test",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        return self.root / payload["audit_path"]

    def test_init_creates_fixed_schema_and_eight_checks(self) -> None:
        audit_path = self.init()
        payload = json.loads(audit_path.read_text(encoding="utf-8"))
        self.assertEqual(payload["schema_version"], "ds-lite.communication-audit.v1")
        self.assertEqual(
            set(payload),
            {
                "schema_version", "audit_id", "skill", "task_class", "profile",
                "detail_mode", "checks", "claims", "protected_content", "handoff",
                "self_check", "result", "extensions",
            },
        )
        self.assertEqual([item["id"] for item in payload["checks"]], [f"honor-{i:02d}" for i in range(1, 9)])
        self.assertEqual(payload["result"]["status"], "in-progress")

    def test_record_check_and_claim_bind_evidence_to_project_relative_hash(self) -> None:
        audit_path = self.init()
        evidence = self.root / "notes" / "事实.txt"
        evidence.parent.mkdir()
        evidence.write_text("observed\n", encoding="utf-8")
        digest = hashlib.sha256(evidence.read_bytes()).hexdigest()
        check = self.run_cli(
            "record-check", "--root", str(self.root), "--audit", "research/artifacts/communication-audit-audit-test.json",
            "--check-id", "honor-01", "--status", "pass", "--evidence-path", "notes/事实.txt",
            "--sha256", digest, "--reason", "read the governing file",
        )
        self.assertEqual(check.returncode, 0, check.stderr)
        claim = self.run_cli(
            "record-claim", "--root", str(self.root), "--audit", str(audit_path),
            "--claim-id", "read-project", "--kind", "read", "--status", "supported",
            "--evidence-path", "notes/事实.txt", "--sha256", digest,
        )
        self.assertEqual(claim.returncode, 0, claim.stderr)
        payload = json.loads(audit_path.read_text(encoding="utf-8"))
        self.assertEqual(payload["checks"][0]["evidence"][0]["sha256"], digest)
        self.assertEqual(payload["claims"][0]["status"], "supported")

    def test_command_evidence_redacts_secret_values_and_keeps_hash(self) -> None:
        audit_path = self.init()
        cases = [
            ("python run.py token=token-value", "token-value"),
            ("python run.py password='password value'", "password value"),
            ("python run.py secret=secret-value", "secret-value"),
            ("python run.py api_key=api-value", "api-value"),
            ("python run.py authorization=authorization-value", "authorization-value"),
            ("curl -H 'Bearer bearer-value' https://example.invalid", "bearer-value"),
        ]
        for command, _ in cases:
            result = self.run_cli(
                "record-check", "--root", str(self.root), "--audit", str(audit_path),
                "--check-id", "honor-05", "--status", "pass", "--reason", "observed",
                "--command", command, "--exit-code", "0", "--observed",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(audit_path.read_text(encoding="utf-8"))
        serialized = json.dumps(payload)
        for _, secret_value in cases:
            self.assertNotIn(secret_value, serialized)
        for evidence in payload["checks"][4]["evidence"]:
            self.assertIn("command_sha256", evidence)
            self.assertEqual(len(evidence["command_sha256"]), 64)

    def test_validate_rejects_absolute_path_unknown_field_and_hidden_reasoning(self) -> None:
        audit_path = self.init()
        payload = json.loads(audit_path.read_text(encoding="utf-8"))
        payload["extensions"]["bad"] = {"path": str(self.root / "x")}
        audit_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        result = self.run_cli("validate", "--root", str(self.root), "--audit", str(audit_path))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("absolute", result.stdout.lower() + result.stderr.lower())

        payload = json.loads(audit_path.read_text(encoding="utf-8"))
        payload["extensions"] = {}
        payload["thought"] = "secret"
        audit_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        result = self.run_cli("validate", "--root", str(self.root), "--audit", str(audit_path))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unknown top-level", result.stdout.lower() + result.stderr.lower())

    def test_validate_rejects_forged_command_evidence_without_hash_or_redaction(self) -> None:
        audit_path = self.init()
        payload = json.loads(audit_path.read_text(encoding="utf-8"))
        payload["checks"][0].update({
            "status": "pass",
            "reason": "observed",
            "evidence": [{
                "command": "python run.py token=should-not-be-stored",
                "exit_code": 0,
                "observed": True,
                "result": "pass",
            }],
        })
        audit_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        result = self.run_cli("validate", "--root", str(self.root), "--audit", str(audit_path))
        self.assertNotEqual(result.returncode, 0)
        combined = result.stdout.lower() + result.stderr.lower()
        self.assertIn("command_sha256", combined)

    def test_validate_rejects_command_hash_mismatch(self) -> None:
        audit_path = self.init()
        command = "python -m pytest"
        payload = json.loads(audit_path.read_text(encoding="utf-8"))
        payload["checks"][0].update({
            "status": "pass",
            "reason": "observed",
            "evidence": [{
                "command": command,
                "command_sha256": "a" * 64,
                "redacted_command_sha256": hashlib.sha256(command.encode("utf-8")).hexdigest(),
                "exit_code": 0,
                "observed": True,
                "result": "pass",
            }],
        })
        audit_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        result = self.run_cli("validate", "--root", str(self.root), "--audit", str(audit_path))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("command_sha256 does not match", result.stdout + result.stderr)

    def test_finalize_requires_all_checks_handoff_and_supported_completion_claims(self) -> None:
        audit_path = self.init()
        result = self.run_cli("finalize", "--root", str(self.root), "--audit", str(audit_path), "--result", "completed")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("check", result.stdout.lower() + result.stderr.lower())

        payload = json.loads(audit_path.read_text(encoding="utf-8"))
        for item in payload["checks"]:
            item.update({"status": "pass", "reason": "observed"})
        payload["claims"] = [{"id": "done", "kind": "completed", "status": "unsupported", "reason": "no evidence"}]
        audit_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        result = self.run_cli("finalize", "--root", str(self.root), "--audit", str(audit_path), "--result", "completed")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unsupported", result.stdout.lower() + result.stderr.lower())

    def test_finalize_blocks_completed_result_without_completed_claim(self) -> None:
        audit_path = self.init()
        payload = json.loads(audit_path.read_text(encoding="utf-8"))
        for item in payload["checks"]:
            item.update({"status": "pass", "reason": "observed"})
        for phase in payload["self_check"].values():
            phase.update({"status": "recorded", "items": ["observed"]})
        payload["handoff"].update({
            "summary": "implemented",
            "next_step": "review",
            "verification": ["C:\\ProgramData\\anaconda3\\Scripts\\pytest.exe -q"],
            "limitations": ["none observed"],
        })
        audit_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        result = self.run_cli("finalize", "--root", str(self.root), "--audit", str(audit_path), "--result", "completed")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("completed claim", result.stdout.lower() + result.stderr.lower())

    def test_finalized_audit_rejects_direct_cli_writes(self) -> None:
        audit_path = self.init()
        payload = json.loads(audit_path.read_text(encoding="utf-8"))
        for item in payload["checks"]:
            item.update({"status": "pass", "reason": "observed"})
        for phase in payload["self_check"].values():
            phase.update({"status": "recorded", "items": ["observed"]})
        payload["handoff"].update({"summary": "blocked audit", "next_step": "user review"})
        audit_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        finalized = self.run_cli(
            "finalize", "--root", str(self.root), "--audit", str(audit_path),
            "--result", "blocked", "--limitation", "host hook unverified",
        )
        self.assertEqual(finalized.returncode, 0, finalized.stderr)
        result = self.run_cli(
            "record-check", "--root", str(self.root), "--audit", str(audit_path),
            "--check-id", "honor-01", "--status", "pass", "--reason", "late write",
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("finalized", result.stdout.lower() + result.stderr.lower())

    def test_supported_verification_rejects_unobserved_or_not_run_command(self) -> None:
        audit_path = self.init()
        result = self.run_cli(
            "record-claim", "--root", str(self.root), "--audit", str(audit_path),
            "--claim-id", "verify", "--kind", "verified", "--status", "supported",
            "--command", "python -m pytest", "--exit-code", "0", "--command-result", "not-run", "--observed",
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("passing observed command evidence", result.stdout.lower() + result.stderr.lower())

    def test_supported_verification_rejects_file_only_evidence(self) -> None:
        audit_path = self.init()
        evidence = self.root / "notes" / "result.txt"
        evidence.parent.mkdir()
        evidence.write_text("pass\n", encoding="utf-8")
        result = self.run_cli(
            "record-claim", "--root", str(self.root), "--audit", str(audit_path),
            "--claim-id", "verify", "--kind", "verified", "--status", "supported",
            "--evidence-path", "notes/result.txt",
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("command evidence", result.stdout.lower() + result.stderr.lower())

    def test_not_applicable_check_requires_a_reason(self) -> None:
        audit_path = self.init()
        result = self.run_cli(
            "record-check", "--root", str(self.root), "--audit", str(audit_path),
            "--check-id", "honor-08", "--status", "not-applicable",
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("reason", result.stdout.lower() + result.stderr.lower())

    def test_changed_protected_content_blocks_completed_academic_rewrite(self) -> None:
        audit_path = self.init()
        payload = json.loads(audit_path.read_text(encoding="utf-8"))
        payload["task_class"] = "academic-rewrite"
        payload["protected_content"] = [{
            "id": "citations", "kind": "citation-key", "before_sha256": "a" * 64,
            "after_sha256": "b" * 64, "status": "changed", "reason": "mismatch",
        }]
        audit_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        result = self.run_cli("validate", "--root", str(self.root), "--audit", str(audit_path))
        self.assertEqual(result.returncode, 0, result.stdout)
        payload = json.loads(audit_path.read_text(encoding="utf-8"))
        for item in payload["checks"]:
            item.update({"status": "pass", "reason": "observed"})
        for phase in payload["self_check"].values():
            phase.update({"status": "recorded", "items": ["recorded"]})
        payload["handoff"].update({"summary": "rewrite", "next_step": "review"})
        audit_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        result = self.run_cli("finalize", "--root", str(self.root), "--audit", str(audit_path), "--result", "completed")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("protected", result.stdout.lower() + result.stderr.lower())

    def test_completed_deep_repository_change_requires_verification_and_limitations(self) -> None:
        audit_path = self.init()
        payload = json.loads(audit_path.read_text(encoding="utf-8"))
        payload["detail_mode"] = "deep"
        for item in payload["checks"]:
            item.update({"status": "pass", "reason": "observed"})
        for phase in payload["self_check"].values():
            phase.update({"status": "recorded", "items": ["observed"]})
        payload["handoff"].update({"summary": "implemented", "next_step": "review"})
        audit_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        result = self.run_cli("finalize", "--root", str(self.root), "--audit", str(audit_path), "--result", "completed")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("verification", result.stdout.lower() + result.stderr.lower())

    def test_finalize_and_render_accept_observed_handoff(self) -> None:
        audit_path = self.init()
        payload = json.loads(audit_path.read_text(encoding="utf-8"))
        for item in payload["checks"]:
            item.update({"status": "pass", "reason": "observed"})
        payload["self_check"] = {
            "before": {"status": "recorded", "items": ["recorded"]},
            "after": {"status": "recorded", "items": ["recorded"]},
            "before_handoff": {"status": "recorded", "items": ["recorded"]},
        }
        payload["handoff"] = {
            "summary": "audit complete", "evidence_paths": [], "verification": ["not run"],
            "limitations": ["host hook unverified"], "next_step": "user review",
        }
        command = "python -m pytest"
        payload["claims"] = [{
            "id": "verified",
            "kind": "verified",
            "status": "supported",
            "evidence": [{
                "command": command,
                "command_sha256": hashlib.sha256(command.encode("utf-8")).hexdigest(),
                "redacted_command_sha256": hashlib.sha256(command.encode("utf-8")).hexdigest(),
                "exit_code": 0,
                "observed": True,
                "result": "pass",
            }],
        }]
        audit_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        result = self.run_cli("finalize", "--root", str(self.root), "--audit", str(audit_path), "--result", "blocked")
        self.assertEqual(result.returncode, 0, result.stderr)
        rendered = self.run_cli("render", "--root", str(self.root), "--audit", str(audit_path))
        self.assertEqual(rendered.returncode, 0, rendered.stderr)
        self.assertIn("honor-01", rendered.stdout)
        self.assertIn("host hook unverified", rendered.stdout)

    def test_completed_audit_accepts_supported_completion_claim(self) -> None:
        audit_path = self.init()
        payload = json.loads(audit_path.read_text(encoding="utf-8"))
        for item in payload["checks"]:
            item.update({"status": "pass", "reason": "observed"})
        for phase in payload["self_check"].values():
            phase.update({"status": "recorded", "items": ["observed"]})
        payload["handoff"].update({"summary": "implemented", "next_step": "review"})
        audit_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        claim = self.run_cli(
            "record-claim", "--root", str(self.root), "--audit", str(audit_path),
            "--claim-id", "complete", "--kind", "completed", "--status", "supported",
            "--command", "python -m pytest", "--exit-code", "0", "--observed",
        )
        self.assertEqual(claim.returncode, 0, claim.stderr)
        result = self.run_cli(
            "finalize", "--root", str(self.root), "--audit", str(audit_path),
            "--result", "completed", "--verification", "python -m pytest: pass",
            "--limitation", "none observed",
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
