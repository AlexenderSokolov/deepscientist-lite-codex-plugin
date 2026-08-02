from __future__ import annotations

import hashlib
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from teaching.control_plane_phase4_evidence import backup_probe, decide, verifier_matrix
from ds_lite_control.store import ControlStore


def _write(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


class Phase4EvidenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="ds-lite-phase4-decision-")
        self.root = Path(self.temp.name)
        self.previous = self.root / "phase3-decision.json"
        self.previous.write_text("phase3 receipt\n", encoding="utf-8")
        self.previous_hash = hashlib.sha256(self.previous.read_bytes()).hexdigest()
        self.paths = {
            "verifier": self.root / "verifier-matrix.json",
            "fault": self.root / "reviewer-fault-matrix.json",
            "real": self.root / "real-reviewer-smoke.json",
            "status": self.root / "status-traceability.json",
            "backup": self.root / "backup-recovery.json",
            "aggregate": self.root / "project-release-aggregate.json",
            "core": self.root / "core-validation.json",
        }
        _write(self.paths["verifier"], {"status": "passed", "protected_claims_ignored": True})
        _write(self.paths["fault"], {"status": "passed", "trials": 100, "cases": {
            name: {"all_passed": True} for name in (
                "verifier-receipt-before-index", "review-terminal-before-sidecar",
                "sidecar-before-index", "aggregate-receipt-before-index",
            )
        }})
        _write(self.paths["real"], {"status": "passed", "evidence_class": "real-codex-independent-reviewer", "checks": {
            name: True for name in (
                "independent_reviewer_thread", "single_reviewer_turn", "read_only_wire",
                "never_approve_wire", "single_canary_thread", "single_canary_turn",
                "canary_read_only_wire", "canary_never_approve_wire",
                "write_canary_command_observed", "write_canary_denied",
                "artifact_digest_unchanged", "terminal_sidecar", "project_aggregate_blocked",
            )
        }, "codex_version": "0.146.0-alpha.3.1", "schema_sha256": "s" * 64,
            "home_mode": "ambient", "raw_model_text_in_receipt": False,
            "controller_inspected_copied_or_modified_credentials": False,
            "workflow_registry_sha256": "w" * 64})
        _write(self.paths["status"], {
            "status": "passed", "all_conclusions_sourced": True,
            "managed_doctor_allowed": True,
            "project_status_schema": "ds-lite.project-status.v3",
            "release_allowed": False,
        })
        _write(self.paths["backup"], {"status": "passed", "backup_schema": "ds-lite.control-backup.v5",
                                      "restore_valid": True})
        _write(self.paths["aggregate"], {"status": "blocked", "release_allowed": False,
                                         "fixture_only": False})
        _write(self.paths["core"], {"status": "passed"})
        self.tests = self.root / "tests.txt"
        self.tests.write_text("Ran 42 tests in 1.0s\n\nOK\n", encoding="utf-8")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _decide(self, output: Path):
        return decide(
            previous=self.previous, expected_previous_hash=self.previous_hash,
            verifier=self.paths["verifier"], fault=self.paths["fault"],
            real_reviewer=self.paths["real"], status=self.paths["status"],
            backup=self.paths["backup"], aggregate=self.paths["aggregate"],
            tests=self.tests, core=self.paths["core"], output=output,
        )

    def test_go_requires_real_reviewer_and_keeps_project_release_blocked(self) -> None:
        result = self._decide(self.root / "phase4-decision.json")

        self.assertEqual(result["phase4_decision"], "go")
        self.assertTrue(result["phase5_goal_allowed"])
        self.assertFalse(result["release_allowed"])

    def test_missing_real_canary_observation_fails_closed(self) -> None:
        payload = json.loads(self.paths["real"].read_text(encoding="utf-8"))
        payload["checks"]["write_canary_denied"] = False
        _write(self.paths["real"], payload)

        result = self._decide(self.root / "phase4-decision-no-go.json")

        self.assertEqual(result["phase4_decision"], "no-go")
        self.assertFalse(result["phase5_goal_allowed"])

    def test_missing_failed_step_artifact_still_writes_no_go_receipt(self) -> None:
        self.paths["backup"].unlink()

        result = self._decide(self.root / "phase4-decision-missing.json")

        self.assertEqual(result["phase4_decision"], "no-go")
        self.assertFalse(result["checks"]["backup_v5_recovery"])
        self.assertFalse(result["artifacts"]["backup_recovery"]["present"])

    def test_decision_output_is_exclusive_create(self) -> None:
        output = self.root / "phase4-decision.json"
        self._decide(output)
        with self.assertRaises(FileExistsError):
            self._decide(output)

    def test_verifier_matrix_ignores_claims_and_fails_closed_on_invalid_inputs(self) -> None:
        result = verifier_matrix(
            self.root / "verifier-work-real", self.root / "verifier-matrix-real.json"
        )

        self.assertEqual(result["status"], "passed")
        self.assertTrue(result["protected_claims_ignored"])
        self.assertTrue(all(result["cases"].values()))
        self.assertFalse(result["release_allowed"])

    def test_backup_probe_restores_v5_bundle_to_new_directory(self) -> None:
        state = self.root / "state"
        state.mkdir()
        store = ControlStore(state / "control.sqlite3")
        store.close()
        runtime = sqlite3.connect(state / "runtime.sqlite3")
        runtime.execute("CREATE TABLE witness(value TEXT)")
        runtime.commit()
        runtime.close()
        for name in ("receipts", "evidence", "private-spool", "supervisor"):
            (state / name).mkdir()
        (state / "receipts" / "receipt.json").write_text("{}\n", encoding="utf-8")
        (state / "evidence" / "manifest.json").write_text("{}\n", encoding="utf-8")
        (state / "private-spool" / "witness.bin").write_bytes(b"private witness")
        (state / "protocol-journal.jsonl").write_text(
            '{"sequence":1,"event_hash":"x"}\n', encoding="utf-8"
        )
        (state / "broker-metadata.json").write_text(
            '{"broker_id":"broker"}\n', encoding="utf-8"
        )
        (state / "supervisor" / "supervisor-state.json").write_text(
            '{"state":"not-installed"}\n', encoding="utf-8"
        )

        result = backup_probe(
            state, self.root / "backup-work-real", self.root / "backup-recovery-real.json"
        )

        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["backup_schema"], "ds-lite.control-backup.v5")
        self.assertTrue(result["restore_valid"])


if __name__ == "__main__":
    unittest.main()
