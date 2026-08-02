import json
import tempfile
import unittest
from pathlib import Path

from teaching.control_plane_phase1_evidence import artifact_ref, decide_phase1, parse_json_event, summarize_test_run, write_once


class Phase1EvidenceTests(unittest.TestCase):
    def test_parse_json_event_ignores_library_logs_but_requires_named_shape(self):
        output = "library log\n" + json.dumps({"status": "completed", "workflow_id": "action-1"}) + "\n"
        self.assertEqual(parse_json_event(output, required_key="workflow_id")["workflow_id"], "action-1")
        self.assertIsNone(parse_json_event("library log\n", required_key="workflow_id"))

    def test_decision_go_requires_every_phase1_gate_and_never_allows_release(self):
        fault = {"status": "passed", "trials": 100, "source_stable": True, "cases": {
            name: {"all_passed": True, "passed": 100} for name in ("K1", "K2", "K3", "K8", "K9")
        }}
        managed = {
            "status": "passed", "python_version": "3.13.5", "dbos_version": "2.29.0",
            "workflow_row_count": 1, "same_action_workflow_identity": True,
            "backup_restore_valid": True, "domain_integrity": "ok", "runtime_integrity": "ok",
            "source_stable": True,
        }
        tests = {"status": "passed", "failures": 0}
        decision = decide_phase1(fault=fault, managed=managed, tests=tests, core=tests,
                                 baseline_hash_matches=True)
        self.assertEqual(decision["phase1_decision"], "go")
        self.assertTrue(decision["phase2_goal_allowed"])
        self.assertFalse(decision["release_allowed"])
        managed["backup_restore_valid"] = False
        self.assertEqual(decide_phase1(fault=fault, managed=managed, tests=tests, core=tests,
                                       baseline_hash_matches=True)["phase1_decision"], "no-go")

    def test_evidence_is_write_once(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "receipt.json"
            write_once(path, {"status": "blocked"})
            with self.assertRaises(FileExistsError):
                write_once(path, {"status": "passed"})

    def test_test_summary_requires_zero_exit_and_parses_count_without_raw_output(self):
        passed = summarize_test_run(returncode=0, output="Ran 23 tests in 1.2s\nOK\n")
        failed = summarize_test_run(returncode=1, output="Ran 23 tests in 1.2s\nFAILED (failures=1)\n")
        self.assertEqual(passed["tests_run"], 23)
        self.assertEqual(passed["status"], "passed")
        self.assertEqual(failed["failures"], 1)
        self.assertFalse(passed["raw_output_persisted"])

    def test_artifact_ref_contains_only_name_hash_and_evidence_class(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "receipt.json"
            path.write_text("{}\n", encoding="utf-8")
            ref = artifact_ref(path, "offline-test")
            self.assertEqual(set(ref), {"name", "sha256", "evidence_class"})
            self.assertEqual(ref["name"], "receipt.json")


if __name__ == "__main__":
    unittest.main()
