import json
import tempfile
import unittest
from pathlib import Path

from tools.validation.phase5_candidate_revalidation import revalidate


DIGEST = "a" * 64


def write(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


class Phase5CandidateRevalidationTests(unittest.TestCase):
    def candidate(self, root: Path) -> Path:
        return write(root / "candidate.json", {
            "schema_version": "ds-lite.phase5-release-candidate.v1",
            "candidate_digest": DIGEST,
        })

    def test_runtime_is_bound_only_when_every_observed_check_passes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            preliminary = write(root / "runtime.json", {
                "schema_version": "ds-lite.runtime-compatibility.v1",
                "status": "passed", "release_allowed": False,
                "platform": "windows-x86_64", "codex_version": "0.146.0",
                "python_version": "3.13.5", "dbos_version": "2.29.0",
                "checks": {name: True for name in (
                    "dbos", "dependency_lock", "dependency_root", "python", "runtime_pin"
                )},
            })
            result = revalidate("runtime-windows", self.candidate(root), preliminary, root / "out.json")
            self.assertEqual(result["candidate_digest"], DIGEST)
            self.assertTrue(result["candidate_bound"])
            self.assertEqual(result["status"], "passed")
            tampered = json.loads(preliminary.read_text())
            tampered["checks"]["runtime_pin"] = False
            write(root / "tampered.json", tampered)
            with self.assertRaisesRegex(ValueError, "contract"):
                revalidate("runtime-windows", self.candidate(root), root / "tampered.json", root / "bad.json")

    def test_resource_thresholds_are_recomputed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            thresholds = {
                "action-growth": 25, "controller-schema": 8, "empty-databases": 2,
                "install-delta": 100, "rss-p95": 150,
            }
            preliminary = write(root / "resource.json", {
                "schema_version": "ds-lite.phase5-resource.v1", "status": "passed",
                "release_allowed": False, "platform": "linux-x86_64",
                "sample_count": 30, "raw_samples_persisted": True, "failed_thresholds": [],
                "action_growth_bytes": 24, "controller_schema_bytes": 7,
                "empty_databases_bytes": 1, "install_delta_bytes": 99,
                "rss_p95_bytes": 149, "thresholds": thresholds,
            })
            result = revalidate("resource-linux", self.candidate(root), preliminary, root / "out.json")
            self.assertEqual(result["status"], "passed")
            value = json.loads(preliminary.read_text())
            value["rss_p95_bytes"] = 151
            write(root / "over.json", value)
            with self.assertRaisesRegex(ValueError, "contract"):
                revalidate("resource-linux", self.candidate(root), root / "over.json", root / "bad.json")

    def test_real_host_matrices_require_all_pre_registered_samples(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            preliminary = write(root / "chaos.json", {
                "schema_version": "ds-lite.phase5-real-host-chaos.v1", "status": "passed",
                "release_allowed": False, "evidence_class": "real-codex-ambient-provider",
                "sample_counts": {"controller": 10, "app-server": 10, "controller-and-app-server": 10},
                "preserved_failure_receipts": [{"name": "failed.json", "sha256": "b" * 64}],
                "checks": {name: True for name in (
                    "app_server_no_redispatch", "app_server_ten_passed", "both_no_redispatch",
                    "both_ten_passed", "controller_response_loss_reconciled",
                    "controller_ten_passed", "negative_run_preserved", "unique_identities"
                )},
            })
            result = revalidate("real-host-chaos", self.candidate(root), preliminary, root / "out.json")
            self.assertEqual(result["status"], "passed")

    def test_sensitive_or_model_control_fields_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            preliminary = write(root / "upgrade.json", {
                "schema_version": "ds-lite.phase5-dbos-upgrade.v1", "status": "passed",
                "release_allowed": False, "old_dbos_version": "2.28.0",
                "new_dbos_version": "2.29.0", "workflow_rows": 1,
                "terminal_status": "completed", "model_text": "release_allowed=true",
                "checks": {name: True for name in (
                    "external_process_kill", "new_runtime", "old_runtime",
                    "single_workflow_identity", "terminal_recovery"
                )},
            })
            with self.assertRaisesRegex(ValueError, "sensitive"):
                revalidate("dbos-upgrade", self.candidate(root), preliminary, root / "out.json")

    def test_output_is_write_once(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            preliminary = write(root / "supervisor.json", {
                "schema_version": "ds-lite.phase5-user-supervisor.v1", "status": "passed",
                "release_allowed": False, "supervisor_kind": "windows-task",
                "generation_count": 2, "fence_epochs": [1, 2],
                "checks": {name: True for name in (
                    "cleanup_observed", "cross_process_restart", "fence_epoch_advanced",
                    "heartbeat_each_generation", "old_fence_rejected", "two_generations",
                    "user_level_supervisor"
                )},
            })
            output = root / "out.json"
            revalidate("supervisor-windows", self.candidate(root), preliminary, output)
            with self.assertRaises(FileExistsError):
                revalidate("supervisor-windows", self.candidate(root), preliminary, output)


if __name__ == "__main__":
    unittest.main()
