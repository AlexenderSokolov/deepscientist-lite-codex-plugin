from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTROLLER_ROOT = ROOT / "plugins" / "deepscientist-lite-core" / "controller"
sys.path.insert(0, str(CONTROLLER_ROOT))

from ds_lite_control.evidence import EvidenceError, EvidenceManager
from ds_lite_control.backup import backup_control_plane, restore_control_plane, verify_backup
from ds_lite_control.release import GateDecisionEngine, StrictReleaseAggregate
from ds_lite_control.app_server import RpcObservation
from ds_lite_control.review import BrokerReviewRunner, ReviewCoordinator, ReviewError, ReviewSidecar
from ds_lite_control.scheduler import DagScheduler
from ds_lite_control.failure_policy import FailureClassifier
from ds_lite_control.store import ControlStore
from ds_lite_control.verification import DeterministicVerifier


class Phase4FoundationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="ds-lite-phase4-")
        self.root = Path(self.temporary.name)
        self.store = ControlStore(self.root / "control.sqlite3")
        self.epoch = self.store.create_job_work_item("job-1", "gate-a", "owner-1")
        self.artifacts = self.root / "artifacts"
        self.artifacts.mkdir()
        (self.artifacts / "result.json").write_text(
            json.dumps({
                "schema_version": "fixture.result.v1",
                "measurement": 42,
                "passed": True,
                "release_allowed": True,
            }),
            encoding="utf-8",
        )
        self.policy = {
            "schema_version": "ds-lite.gate-policy.v1",
            "policy_id": "measurement-policy-v1",
            "minimum_evidence_class": "offline",
            "required_artifacts": [{
                "path": "result.json",
                "schema_version": "fixture.result.v1",
                "required_fields": {"measurement": 42},
            }],
        }

    def tearDown(self) -> None:
        self.store.close()
        self.temporary.cleanup()

    def test_new_database_uses_schema_v4_and_evidence_tables(self) -> None:
        self.assertEqual(self.store.schema_version, 4)
        tables = {
            row[0]
            for row in self.store.connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        self.assertTrue({
            "evidence_sets", "evidence_members", "verifier_runs",
            "review_requests", "review_results", "gate_decisions",
            "release_profiles", "release_decisions", "private_witness_index",
            "integrity_incidents",
        } <= tables)

    def test_freeze_manifest_is_idempotent_and_path_escape_is_rejected(self) -> None:
        manager = EvidenceManager(
            self.store,
            self.root / "evidence",
            self.root / "private-spool",
        )
        first = manager.freeze(
            "job-1", "gate-a", self.artifacts, self.policy,
            evidence_class="offline", owner_id="owner-1", fence_epoch=self.epoch,
        )
        second = manager.freeze(
            "job-1", "gate-a", self.artifacts, self.policy,
            evidence_class="offline", owner_id="owner-1", fence_epoch=self.epoch,
        )
        self.assertEqual(first["evidence_set_id"], second["evidence_set_id"])
        self.assertEqual(first["manifest_hash"], second["manifest_hash"])
        self.assertEqual(first["members"][0]["path"], "result.json")
        escaped = dict(self.policy)
        escaped["required_artifacts"] = [{"path": "../outside.json"}]
        with self.assertRaises(EvidenceError):
            manager.freeze(
                "job-1", "gate-a", self.artifacts, escaped,
                evidence_class="offline", owner_id="owner-1", fence_epoch=self.epoch,
            )
        (self.artifacts / "sensitive.json").write_text(
            json.dumps({"schema_version": "fixture.result.v1", "token": "redacted"}),
            encoding="utf-8",
        )
        sensitive = dict(self.policy)
        sensitive["required_artifacts"] = [{"path": "sensitive.json"}]
        with self.assertRaisesRegex(EvidenceError, "sensitive"):
            manager.freeze(
                "job-1", "gate-a", self.artifacts, sensitive,
                evidence_class="offline", owner_id="owner-1", fence_epoch=self.epoch,
            )

    def test_verifier_uses_policy_not_worker_pass_or_release_fields(self) -> None:
        manager = EvidenceManager(
            self.store,
            self.root / "evidence",
            self.root / "private-spool",
        )
        manifest = manager.freeze(
            "job-1", "gate-a", self.artifacts, self.policy,
            evidence_class="offline", owner_id="owner-1", fence_epoch=self.epoch,
        )
        verifier = DeterministicVerifier(self.store, self.root / "receipts")
        receipt = verifier.verify(
            "gate-a", manifest["evidence_set_id"], self.policy,
            owner_id="owner-1", fence_epoch=self.epoch,
        )
        self.assertEqual(receipt["status"], "passed")
        self.assertIn("protected-claim-ignored", receipt["check_codes"])
        self.assertNotIn("release_allowed", receipt)
        self.assertNotIn("gate_passed", receipt)

    def test_review_sidecar_rejects_release_and_requires_known_evidence_refs(self) -> None:
        valid = {
            "schema_version": "ds-lite.review-sidecar.v1",
            "verdict": "accept",
            "finding_codes": [],
            "evidence_refs": ["result.json"],
        }
        self.assertEqual(
            ReviewSidecar.validate(valid, allowed_refs={"result.json"})["verdict"],
            "accept",
        )
        invalid = dict(valid, release_allowed=True)
        with self.assertRaises(ReviewError):
            ReviewSidecar.validate(invalid, allowed_refs={"result.json"})
        unknown = dict(valid, evidence_refs=["missing.json"])
        with self.assertRaises(ReviewError):
            ReviewSidecar.validate(unknown, allowed_refs={"result.json"})

    def test_strict_aggregate_is_blocked_without_deterministic_gate_decision(self) -> None:
        aggregate = StrictReleaseAggregate(self.store, self.root / "receipts")
        profile = {
            "schema_version": "ds-lite.release-profile.v1",
            "profile_id": "project-phase5-readiness",
            "required_gates": ["gate-a", "gate-b"],
            "fixture_only": False,
        }
        decision = aggregate.decide("job-1", profile)
        self.assertEqual(decision["status"], "blocked")
        self.assertFalse(decision["release_allowed"])
        self.assertEqual(decision["missing_gates"], ["gate-a", "gate-b"])

    def _verified_manifest(self) -> tuple[dict, dict]:
        manager = EvidenceManager(
            self.store, self.root / "evidence", self.root / "private-spool"
        )
        manifest = manager.freeze(
            "job-1", "gate-a", self.artifacts, self.policy,
            evidence_class="offline", owner_id="owner-1", fence_epoch=self.epoch,
        )
        receipt = DeterministicVerifier(self.store, self.root / "receipts").verify(
            "gate-a", manifest["evidence_set_id"], self.policy,
            owner_id="owner-1", fence_epoch=self.epoch,
        )
        return manifest, receipt

    def test_reviewer_is_independent_write_once_and_artifact_preserving(self) -> None:
        manifest, verifier = self._verified_manifest()
        coordinator = ReviewCoordinator(self.store, self.root / "receipts")
        request = coordinator.prepare(
            "gate-a", manifest["evidence_set_id"], verifier["verifier_id"],
            schema_digest="s" * 64, model="gpt-5.6-sol",
            owner_id="owner-1", fence_epoch=self.epoch,
        )
        coordinator.bind_thread(
            request["review_id"], "review-thread-1", worker_thread_ids={"worker-thread-1"},
            owner_id="owner-1", fence_epoch=self.epoch,
        )
        with self.assertRaises(ReviewError):
            coordinator.bind_thread(
                request["review_id"], "review-thread-2", worker_thread_ids=set(),
                owner_id="owner-1", fence_epoch=self.epoch,
            )
        result = coordinator.record_result(
            request["review_id"], {
                "schema_version": "ds-lite.review-sidecar.v1",
                "verdict": "accept",
                "finding_codes": [],
                "evidence_refs": ["result.json"],
            },
            post_manifest_hash=manifest["manifest_hash"], reviewer_turn_id="review-turn-1",
            owner_id="owner-1", fence_epoch=self.epoch,
        )
        self.assertEqual(result["verdict"], "accept")
        self.assertNotIn("release_allowed", result)
        changed = dict(result, verdict="reject")
        with self.assertRaises(ReviewError):
            coordinator.record_result(
                request["review_id"], changed,
                post_manifest_hash=manifest["manifest_hash"], reviewer_turn_id="review-turn-1",
                owner_id="owner-1", fence_epoch=self.epoch,
            )

    def test_gate_decision_and_fixture_aggregate_are_deterministic(self) -> None:
        manifest, verifier = self._verified_manifest()
        coordinator = ReviewCoordinator(self.store, self.root / "receipts")
        request = coordinator.prepare(
            "gate-a", manifest["evidence_set_id"], verifier["verifier_id"],
            schema_digest="s" * 64, model="gpt-5.6-sol",
            owner_id="owner-1", fence_epoch=self.epoch,
        )
        coordinator.bind_thread(
            request["review_id"], "review-thread-1", worker_thread_ids=set(),
            owner_id="owner-1", fence_epoch=self.epoch,
        )
        coordinator.record_result(
            request["review_id"], {
                "schema_version": "ds-lite.review-sidecar.v1", "verdict": "accept",
                "finding_codes": [], "evidence_refs": ["result.json"],
            },
            post_manifest_hash=manifest["manifest_hash"], reviewer_turn_id="review-turn-1",
            owner_id="owner-1", fence_epoch=self.epoch,
        )
        gate = GateDecisionEngine(self.store, self.root / "receipts").decide(
            "gate-a", manifest["evidence_set_id"], request["review_id"],
            owner_id="owner-1", fence_epoch=self.epoch,
        )
        self.assertEqual(gate["status"], "passed")
        fixture = StrictReleaseAggregate(self.store, self.root / "receipts").decide(
            "job-1", {
                "schema_version": "ds-lite.release-profile.v1",
                "profile_id": "fixture-profile", "required_gates": ["gate-a"],
                "fixture_only": True,
            }
        )
        self.assertTrue(fixture["release_allowed"])
        project = StrictReleaseAggregate(self.store, self.root / "receipts").decide(
            "job-1", {
                "schema_version": "ds-lite.release-profile.v1",
                "profile_id": "project-profile", "required_gates": ["gate-a", "phase5-host"],
                "fixture_only": False,
            }
        )
        self.assertFalse(project["release_allowed"])

    def test_release_materialization_is_fenced_write_once_and_rejects_fixtures(self) -> None:
        aggregate = StrictReleaseAggregate(self.store, self.root / "receipts")
        epoch = self.store.acquire_lease("job-1", "release-owner")
        profile = {
            "schema_version": "ds-lite.release-profile.v1",
            "profile_id": "project-phase5-readiness",
            "required_gates": ["gate-a", "phase5-host"],
            "fixture_only": False,
        }
        first = aggregate.materialize(
            "job-1", profile, owner_id="release-owner", fence_epoch=epoch
        )
        second = aggregate.materialize(
            "job-1", profile, owner_id="release-owner", fence_epoch=epoch
        )
        self.assertEqual(first["receipt_hash"], second["receipt_hash"])
        self.assertFalse(first["release_allowed"])
        self.assertEqual(
            self.store.project_job_status("job-1")["release"]["source_receipt"],
            first["receipt_id"],
        )
        fixture = dict(profile, profile_id="fixture-profile", fixture_only=True)
        with self.assertRaisesRegex(ValueError, "fixture"):
            aggregate.materialize(
                "job-1", fixture, owner_id="release-owner", fence_epoch=epoch
            )

    def test_integrity_incident_pauses_new_dispatch_and_status_has_sources(self) -> None:
        self.store.record_integrity_incident(
            "incident-1", scope="evidence", entity_id="gate-a",
            reason_code="artifact-drift", evidence_hash="d" * 64,
        )
        scheduler = DagScheduler(self.store, FailureClassifier(seed=20260731))
        with self.assertRaisesRegex(Exception, "integrity"):
            scheduler.claim_ready("job-1", "owner-1")
        status = self.store.project_job_status("job-1")
        self.assertEqual(status["schema_version"], "ds-lite.project-status.v3")
        self.assertFalse(status["release"]["release_allowed"])
        self.assertTrue(status["integrity"]["dispatch_paused"])
        self.assertTrue(all("sources" in gate for gate in status["gates"]))

    def test_private_spool_rejects_credentials_and_exposes_only_metadata(self) -> None:
        manager = EvidenceManager(
            self.store, self.root / "evidence", self.root / "private-spool"
        )
        metadata = manager.store_private_witness(
            "gate-a", "review-transcript", b"redacted reviewer event",
            owner_id="owner-1", fence_epoch=self.epoch,
        )
        self.assertNotIn("path", metadata)
        self.assertNotIn("content", metadata)
        with self.assertRaises(EvidenceError):
            manager.store_private_witness(
                "gate-a", "review-transcript", b"Authorization: Bearer secret",
                owner_id="owner-1", fence_epoch=self.epoch,
            )

    def test_backup_v5_requires_and_restores_evidence_and_private_spool(self) -> None:
        state = self.root / "state"
        state.mkdir()
        backup_store = ControlStore(state / "control.sqlite3")
        backup_store.close()
        import sqlite3
        sqlite3.connect(state / "runtime.sqlite3").close()
        for directory in ("receipts", "evidence", "private-spool", "supervisor"):
            (state / directory).mkdir()
        (state / "receipts" / "one.json").write_text("{}\n", encoding="utf-8")
        (state / "evidence" / "manifest.json").write_text("{}\n", encoding="utf-8")
        (state / "private-spool" / "witness.bin").write_bytes(b"redacted")
        (state / "protocol-journal.jsonl").write_text(
            '{"sequence":1,"entry_hash":"x"}\n', encoding="utf-8"
        )
        (state / "broker-metadata.json").write_text(
            '{"broker_id":"broker-1"}\n', encoding="utf-8"
        )
        (state / "supervisor" / "supervisor-state.json").write_text(
            '{"state":"stopped"}\n', encoding="utf-8"
        )
        backup = self.root / "backup"
        manifest = backup_control_plane(
            state, backup, require_protocol=True, require_broker=True,
            require_supervisor=True, require_evidence=True,
        )
        self.assertEqual(manifest["schema_version"], "ds-lite.control-backup.v5")
        self.assertTrue(verify_backup(backup)["valid"])
        restored = self.root / "restored"
        self.assertTrue(restore_control_plane(backup, restored)["valid"])
        self.assertEqual((restored / "private-spool" / "witness.bin").read_bytes(), b"redacted")

    def test_broker_reviewer_uses_one_read_only_thread_and_one_turn(self) -> None:
        manifest, verifier = self._verified_manifest()
        coordinator = ReviewCoordinator(self.store, self.root / "receipts")
        request = coordinator.prepare(
            "gate-a", manifest["evidence_set_id"], verifier["verifier_id"],
            schema_digest="s" * 64, model="gpt-5.6-sol",
            owner_id="owner-1", fence_epoch=self.epoch,
        )

        class FakeAdapter:
            def __init__(self) -> None:
                self.thread_starts = 0
                self.turn_starts = 0
                self.thread_params = None

            def initialize(self, *, request_id: str):
                return RpcObservation("initialize", request_id, 1, {}, None, None, "acknowledged")

            def start_thread(self, params, *, request_id: str):
                self.thread_starts += 1
                self.thread_params = params
                return RpcObservation(
                    "thread/start", request_id, 2,
                    {"result": {"thread": {"id": "review-thread-1"}}},
                    "review-thread-1", None, "acknowledged",
                )

            def start_turn(self, thread_id, input_items, *, request_id: str, model=None):
                self.turn_starts += 1
                return RpcObservation(
                    "turn/start", request_id, 3,
                    {"result": {"turn": {"id": "review-turn-1"}}},
                    thread_id, "review-turn-1", "acknowledged",
                )

            def observe_turn(self, thread_id, turn_id, *, timeout: float):
                return RpcObservation(
                    "turn/observe", "observe", 0,
                    {"method": "turn/completed", "params": {
                        "threadId": thread_id, "turn": {"id": turn_id, "status": "completed"},
                    }}, thread_id, turn_id, "terminal",
                )

            def read_thread(self, thread_id, *, include_turns=True, request_id="thread-read"):
                text = json.dumps({
                    "schema_version": "ds-lite.review-sidecar.v1", "verdict": "accept",
                    "finding_codes": [], "evidence_refs": ["result.json"],
                })
                return RpcObservation(
                    "thread/read", request_id, 4,
                    {"result": {"thread": {"id": thread_id, "turns": [{
                        "id": "review-turn-1", "items": [{"type": "agentMessage", "text": text}],
                    }]}}}, thread_id, None, "acknowledged",
                )

        adapter = FakeAdapter()
        runner = BrokerReviewRunner(
            self.store, coordinator, adapter,
            private_spool_root=self.root / "private-spool",
        )
        first = runner.run(
            request["review_id"], owner_id="owner-1", fence_epoch=self.epoch,
            observe_timeout=5,
        )
        second = runner.run(
            request["review_id"], owner_id="owner-1", fence_epoch=self.epoch,
            observe_timeout=5,
        )
        self.assertEqual(first["verdict"], "accept")
        self.assertEqual(first["receipt_hash"], second["receipt_hash"])
        self.assertEqual(adapter.thread_starts, 1)
        self.assertEqual(adapter.turn_starts, 1)
        self.assertEqual(adapter.thread_params["sandbox"], "read-only")
        self.assertEqual(adapter.thread_params["approvalPolicy"], "never")
        self.assertFalse(adapter.thread_params["ephemeral"])


if __name__ == "__main__":
    unittest.main()
