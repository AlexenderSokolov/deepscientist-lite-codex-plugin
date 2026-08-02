import json
import hashlib
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from teaching.control_plane_phase2_evidence import decide


class Phase2EvidenceTests(unittest.TestCase):
    def test_real_lifecycle_without_response_loss_or_restart_is_no_go(self):
        with tempfile.TemporaryDirectory(prefix="ds-lite-phase2-decision-") as directory:
            root = Path(directory)
            fault = {"status": "passed", "trials": 100, "seed": 1, "evidence_class": "fake-host-external-process",
                     "cases": {name: {"passed": 100} for name in ("K4", "K5", "K6", "K7", "K12")}}
            smoke = {"status": "passed", "evidence_class": "real-app-server",
                     "response_loss_injected": False, "controller_restart_observed": False}
            managed = {"status": "passed", "backup_restore_valid": True, "evidence_class": "sqlite-backup+fake-host"}
            for name, payload in (("fault", fault), ("smoke", smoke), ("managed", managed)):
                (root / f"{name}.json").write_text(json.dumps(payload), encoding="utf-8")
            (root / "tests.txt").write_text("Ran 1 test\n\nOK\n", encoding="utf-8")
            (root / "core.json").write_text(json.dumps({"status": "passed"}), encoding="utf-8")
            result = decide(
                fault=root / "fault.json", smoke=root / "smoke.json", managed=root / "managed.json",
                tests=root / "tests.txt", core=root / "core.json", output=root / "decision.json",
            )
            self.assertEqual(result["phase2_decision"], "no-go")
            self.assertFalse(result["checks"]["real_response_loss"])
            self.assertFalse(result["checks"]["controller_restart"])
            self.assertFalse(result["phase3_goal_allowed"])
            self.assertTrue(result["checks"]["core_validation"])
            self.assertFalse(result["release_allowed"])

    def test_continuation_go_requires_real_broker_journal_and_previous_receipt(self):
        with tempfile.TemporaryDirectory(prefix="ds-lite-phase2-continuation-") as directory:
            root = Path(directory)
            fault = {"status": "passed", "trials": 100, "seed": 1, "evidence_class": "fake-host-external-process",
                     "cases": {name: {"passed": 100} for name in ("K4", "K5", "K6", "K7", "K12")}}
            smoke = {"status": "passed", "evidence_class": "real-app-server"}
            managed = {"status": "passed", "backup_restore_valid": True, "evidence_class": "sqlite-backup+fake-host"}
            real = {"status": "passed", "evidence_class": "real-app-server-external-controller-processes",
                    "response_loss_injected": True, "controller_restart_observed": True,
                    "pending_archive_recovered": True, "turn_start_count": 3,
                    "checks": {"exactly_three_turn_starts": True, "single_canonical_thread": True,
                               "archive_not_redispatched": True, "response_loss_reconciled": True}}
            journal = {"valid": True, "dropped_response_count": 2,
                       "method_counts": {"turn/start": 3, "thread/archive": 1}}
            phase_contract = {"status": "passed", "cases": []}
            previous = root / "previous.json"
            previous.write_text('{"phase2_decision":"no-go"}\n', encoding="utf-8")
            for name, payload in (("fault", fault), ("smoke", smoke), ("managed", managed),
                                  ("real", real), ("journal", journal), ("phase-contract", phase_contract)):
                (root / f"{name}.json").write_text(json.dumps(payload), encoding="utf-8")
            (root / "tests.txt").write_text("Ran 1 test\n\nOK\n", encoding="utf-8")
            (root / "core.json").write_text(json.dumps({"status": "passed"}), encoding="utf-8")
            expected = hashlib.sha256(previous.read_bytes()).hexdigest()
            result = decide(
                fault=root / "fault.json", smoke=root / "smoke.json", managed=root / "managed.json",
                tests=root / "tests.txt", core=root / "core.json", output=root / "decision.json",
                real_broker=root / "real.json", broker_journal=root / "journal.json",
                previous_decision=previous, expected_previous_sha256=expected,
                phase_contract=root / "phase-contract.json",
            )
            self.assertEqual(result["phase2_decision"], "go")
            self.assertTrue(result["phase3_goal_allowed"])
            self.assertFalse(result["release_allowed"])
            self.assertEqual(
                result["digests"]["codex_schema_sha256"],
                "9e22b7c4174cdaa87fc3240bce6bfecf8855f263eddfed3e97e49cb165527afb",
            )
            self.assertEqual(
                result["evidence_classes"]["real_broker"],
                "real-app-server-external-controller-processes",
            )
