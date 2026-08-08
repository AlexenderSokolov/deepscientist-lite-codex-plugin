#!/usr/bin/env python3
"""Tests for DS Lite v6 mechanisms: Signal Ledger, Frontier, Claim Ledger, Factor Card v2."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from plugins.deepscientist_lite_import_shim import ds_lite_signal_ledger
from plugins.deepscientist_lite_import_shim import ds_lite_frontier
from plugins.deepscientist_lite_import_shim import ds_lite_claim_ledger
from plugins.deepscientist_lite_import_shim import ds_lite_factor_card_v2


class SignalLedgerTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.ledger_path = str(Path(self.root) / "research" / "artifacts" / "signal-ledger-test-ledger.json")

    def test_create_and_append_signal(self):
        ds_lite_signal_ledger.create_ledger("test-ledger", "wu-001", self.root)
        signal = {
            "signal_id": "sig-001",
            "signal_type": "novelty-gap",
            "source_ref": "research/artifacts/scout-001.md",
            "scope": {"work_unit_id": "wu-001", "route_node_id": "node-active"},
            "observation": "No prior work combines X with Y under constraint Z.",
            "confidence": "medium",
            "dependencies": ["sig-000"],
            "expiry": {"type": "on-supersede"},
            "status": "active",
            "created_at": "2026-08-04T10:00:00Z",
            "extensions": {},
        }
        result = ds_lite_signal_ledger.append_signal(self.ledger_path, signal)
        self.assertEqual(result["signal_id"], "sig-001")
        self.assertIn("signal_digest", result)

    def test_duplicate_signal_id_rejected(self):
        ds_lite_signal_ledger.create_ledger("test-ledger-2", "wu-002", self.root)
        ledger_path = str(Path(self.root) / "research" / "artifacts" / "signal-ledger-test-ledger-2.json")
        signal = {
            "signal_id": "sig-dup",
            "signal_type": "evidence-found",
            "source_ref": "ref",
            "scope": {"work_unit_id": "wu-002", "route_node_id": "node"},
            "observation": "obs",
            "confidence": "low",
            "dependencies": [],
            "expiry": {"type": "never"},
            "status": "active",
            "created_at": "2026-08-04T10:00:00Z",
            "extensions": {},
        }
        ds_lite_signal_ledger.append_signal(ledger_path, signal)
        with self.assertRaises(ds_lite_signal_ledger.SignalError):
            ds_lite_signal_ledger.append_signal(ledger_path, signal)

    def test_supersede_signal(self):
        ds_lite_signal_ledger.create_ledger("test-ledger-3", "wu-003", self.root)
        ledger_path = str(Path(self.root) / "research" / "artifacts" / "signal-ledger-test-ledger-3.json")
        for sid in ["sig-a", "sig-b"]:
            signal = {
                "signal_id": sid,
                "signal_type": "evidence-found",
                "source_ref": "ref",
                "scope": {"work_unit_id": "wu-003", "route_node_id": "node"},
                "observation": "obs",
                "confidence": "low",
                "dependencies": [],
                "expiry": {"type": "on-supersede"},
                "status": "active",
                "created_at": "2026-08-04T10:00:00Z",
                "extensions": {},
            }
            ds_lite_signal_ledger.append_signal(ledger_path, signal)
        result = ds_lite_signal_ledger.supersede_signal(ledger_path, "sig-a", "sig-b")
        self.assertEqual(result["status"], "superseded")


class FrontierTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.frontier_path = str(Path(self.root) / "research" / "artifacts" / "discovery-frontier-test-frontier.json")

    def test_create_and_add_candidate(self):
        ds_lite_frontier.create_frontier("test-frontier", "wu-001", self.root)
        candidate = {
            "candidate_id": "cand-001",
            "hypothesis": "Combining X with Y improves Z under budget B.",
            "mechanism": "X provides feature F; Y provides feature G; together they reduce cost C.",
            "differentiation": "No prior work combines X+Y for target Z.",
            "signal_refs": ["sig-001"],
            "factor_card_ref": "research/artifacts/factor-card-001.json",
            "status": "proposed",
            "selection_rationale": "",
            "falsification_prediction": {
                "prediction": "X+Y will outperform X alone on metric M.",
                "falsifier": "If X+Y does not exceed X alone on M, the hypothesis is refuted.",
            },
            "minimal_test_ref": "research/artifacts/factor-card-001.json",
            "extensions": {},
        }
        result = ds_lite_frontier.add_candidate(self.frontier_path, candidate)
        self.assertEqual(result["candidate_id"], "cand-001")
        self.assertIn("candidate_digest", result)

    def test_select_candidate(self):
        ds_lite_frontier.create_frontier("test-frontier-2", "wu-002", self.root)
        frontier_path = str(Path(self.root) / "research" / "artifacts" / "discovery-frontier-test-frontier-2.json")
        candidate = {
            "candidate_id": "cand-002",
            "hypothesis": "h",
            "mechanism": "m",
            "differentiation": "d",
            "signal_refs": [],
            "factor_card_ref": "ref",
            "status": "proposed",
            "selection_rationale": "",
            "falsification_prediction": {"prediction": "p", "falsifier": "f"},
            "minimal_test_ref": "ref",
            "extensions": {},
        }
        ds_lite_frontier.add_candidate(frontier_path, candidate)
        result = ds_lite_frontier.select_candidate(frontier_path, "cand-002", "Best fit for current route.")
        self.assertEqual(result["status"], "selected")

    def test_project_frontier(self):
        ds_lite_frontier.create_frontier("test-frontier-3", "wu-003", self.root)
        frontier_path = str(Path(self.root) / "research" / "artifacts" / "discovery-frontier-test-frontier-3.json")
        projection = ds_lite_frontier.project_frontier(frontier_path)
        self.assertEqual(projection["active_count"], 0)
        self.assertIsNone(projection["selected_candidate"])


class ClaimLedgerTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.ledger_path = str(Path(self.root) / "research" / "artifacts" / "claim-ledger-test-claim-ledger.json")

    def test_create_and_append_claim(self):
        ds_lite_claim_ledger.create_ledger("test-claim-ledger", "wu-001", self.root)
        claim = {
            "claim_id": "claim-001",
            "claim_type": "positive-result",
            "statement": "Method M achieves accuracy A on dataset D.",
            "selector": {"type": "metric", "query": "accuracy > 0.9"},
            "evidence_refs": ["research/evidence/run-001/manifest.json"],
            "dependence_group": "group-a",
            "transformation_chain": [
                {"operation": "train", "input_ref": "data/train.csv", "output_ref": "model.pkl"},
                {"operation": "evaluate", "input_ref": "model.pkl", "output_ref": "metrics.json"},
            ],
            "executed_code_ref": "scripts/run_experiment.py",
            "verifier": {"type": "deterministic", "result": "pass"},
            "fidelity": "medium",
            "status": "supported",
            "created_at": "2026-08-04T10:00:00Z",
            "extensions": {},
        }
        result = ds_lite_claim_ledger.append_claim(self.ledger_path, claim)
        self.assertEqual(result["claim_id"], "claim-001")
        self.assertIn("claim_digest", result)

    def test_confirmatory_claim_requires_pre_registration(self):
        ds_lite_claim_ledger.create_ledger("test-claim-ledger-2", "wu-002", self.root)
        ledger_path = str(Path(self.root) / "research" / "artifacts" / "claim-ledger-test-claim-ledger-2.json")
        claim = {
            "claim_id": "claim-conf",
            "claim_type": "positive-result",
            "statement": "s",
            "selector": {"type": "t", "query": "q"},
            "evidence_refs": ["ref"],
            "dependence_group": "g",
            "transformation_chain": [],
            "executed_code_ref": "",
            "verifier": {"type": "t", "result": "pass"},
            "fidelity": "confirmatory",
            "status": "supported",
            "created_at": "2026-08-04T10:00:00Z",
            "extensions": {},
        }
        with self.assertRaises(ds_lite_claim_ledger.ClaimError):
            ds_lite_claim_ledger.append_claim(ledger_path, claim)

    def test_supersede_claim(self):
        ds_lite_claim_ledger.create_ledger("test-claim-ledger-3", "wu-003", self.root)
        ledger_path = str(Path(self.root) / "research" / "artifacts" / "claim-ledger-test-claim-ledger-3.json")
        for cid in ["claim-a", "claim-b"]:
            claim = {
                "claim_id": cid,
                "claim_type": "positive-result",
                "statement": "s",
                "selector": {"type": "t", "query": "q"},
                "evidence_refs": ["ref"],
                "dependence_group": "g",
                "transformation_chain": [],
                "executed_code_ref": "",
                "verifier": {"type": "t", "result": "pass"},
                "fidelity": "medium",
                "status": "supported",
                "created_at": "2026-08-04T10:00:00Z",
                "extensions": {},
            }
            ds_lite_claim_ledger.append_claim(ledger_path, claim)
        result = ds_lite_claim_ledger.supersede_claim(ledger_path, "claim-a", "claim-b")
        self.assertEqual(result["status"], "superseded")

    def _draft_claim(self, claim_id="claim-review"):
        return {
            "claim_id": claim_id,
            "claim_type": "positive-result",
            "statement": "s",
            "selector": {"type": "metric", "query": "accuracy > 0.9"},
            "evidence_refs": ["research/evidence/run-001/manifest.json"],
            "dependence_group": "g",
            "transformation_chain": [],
            "executed_code_ref": "scripts/run.py",
            "verifier": {"type": "deterministic", "result": "pass"},
            "fidelity": "medium",
            "status": "draft",
            "created_at": "2026-08-04T10:00:00Z",
            "extensions": {},
        }

    def _review(self, claim_id="claim-review", *, verdict="pass", assessment="supportable",
                refs=None):
        return {
            "schema_version": "ds-lite.review-result.v1",
            "review_id": "review-001",
            "work_unit_id": "wu-review",
            "profile_id": "profile-review",
            "review_node_id": "review-001",
            "reviewed_node_id": "iteration-001",
            "reviewed_evidence_refs": refs or ["research/evidence/run-001/manifest.json"],
            "evidence_validator": "validator-001",
            "evidence_digest": "0" * 64,
            "verdict": verdict,
            "claim_assessment": assessment,
            "channels": {"integrity": "pass" if verdict == "pass" else "fail"},
            "limitations": [],
            "review_artifact_ref": "research/artifacts/review-001.json",
            "completed_at": "2026-08-04T10:00:00Z",
            "extensions": {"claim_id": claim_id},
        }

    def test_review_promotion_records_typed_provenance(self):
        ds_lite_claim_ledger.create_ledger("review-ledger", "wu-review", self.root)
        ledger_path = str(Path(self.root) / "research" / "artifacts" / "claim-ledger-review-ledger.json")
        ds_lite_claim_ledger.append_claim(ledger_path, self._draft_claim())
        review_path = Path(self.root) / "research" / "artifacts" / "review-001.json"
        review_path.write_text(json.dumps(self._review()), encoding="utf-8")
        result = ds_lite_claim_ledger.promote_claim_from_review(ledger_path, "claim-review", str(review_path))
        self.assertEqual(result["status"], "supported")
        self.assertEqual(result["extensions"]["review_verdict"], "pass")
        self.assertRegex(result["extensions"]["review_sha256"], r"^[a-f0-9]{64}$")

    def test_review_promotion_rejects_unbound_evidence(self):
        ds_lite_claim_ledger.create_ledger("review-ledger-2", "wu-review", self.root)
        ledger_path = str(Path(self.root) / "research" / "artifacts" / "claim-ledger-review-ledger-2.json")
        ds_lite_claim_ledger.append_claim(ledger_path, self._draft_claim("claim-review-2"))
        review_path = Path(self.root) / "research" / "artifacts" / "review-002.json"
        review_path.write_text(json.dumps(self._review("claim-review-2", refs=["outside.json"])), encoding="utf-8")
        with self.assertRaisesRegex(ds_lite_claim_ledger.ClaimError, "subset"):
            ds_lite_claim_ledger.promote_claim_from_review(ledger_path, "claim-review-2", str(review_path))

    def test_refuted_review_marks_claim_contested(self):
        ds_lite_claim_ledger.create_ledger("review-ledger-3", "wu-review", self.root)
        ledger_path = str(Path(self.root) / "research" / "artifacts" / "claim-ledger-review-ledger-3.json")
        ds_lite_claim_ledger.append_claim(ledger_path, self._draft_claim("claim-review-3"))
        review_path = Path(self.root) / "research" / "artifacts" / "review-003.json"
        review_path.write_text(json.dumps(self._review("claim-review-3", verdict="fail", assessment="refuted")), encoding="utf-8")
        result = ds_lite_claim_ledger.promote_claim_from_review(ledger_path, "claim-review-3", str(review_path))
        self.assertEqual(result["status"], "contested")


class FactorCardV2Tests(unittest.TestCase):
    def test_validate_valid_card(self):
        card = {
            "schema_version": "ds-lite.factor-card.v2",
            "factor_card_id": "fc-001",
            "work_unit_id": "wu-001",
            "profile_id": "prof-001",
            "subject_ref": "research/artifacts/idea-001.json",
            "status": "assessed",
            "decision": "explore",
            "factors": [
                {"name": "novelty", "score": 3, "confidence": "medium", "evidence_refs": ["ref"], "summary": "Novel combination.", "uncertainty": ["Search scope limited."], "extensions": {}},
                {"name": "feasibility", "score": 2, "confidence": "low", "evidence_refs": ["ref"], "summary": "Requires tool T.", "uncertainty": ["Tool availability unknown."], "extensions": {}},
                {"name": "evidence_strength", "score": None, "confidence": "unknown", "evidence_refs": [], "summary": "No evidence yet.", "uncertainty": [], "extensions": {}},
                {"name": "cost", "score": 1, "confidence": "high", "evidence_refs": ["ref"], "summary": "Low cost.", "uncertainty": [], "extensions": {}},
                {"name": "risk", "score": 2, "confidence": "medium", "evidence_refs": ["ref"], "summary": "Moderate risk.", "uncertainty": [], "extensions": {}},
                {"name": "alignment", "score": 4, "confidence": "high", "evidence_refs": ["ref"], "summary": "Directly aligned.", "uncertainty": [], "extensions": {}},
            ],
            "lineage": {"source_type": "novel", "parent_refs": []},
            "differentiation_axes": [
                {"axis": "mechanism", "description": "Uses X instead of Y.", "closest_known": "Prior work W"},
            ],
            "recent_work": [
                {"ref": "doi:10.1000/example", "relation": "competing"},
            ],
            "falsification_predictions": [
                {"prediction": "X+Y outperforms X alone on M.", "falsifier": "If not, refuted.", "expected_outcome": "confirmed"},
            ],
            "signal_refs": ["sig-001"],
            "selection_rationale": "Highest novelty and alignment with acceptable cost.",
            "minimal_test": {
                "question": "Does X+Y outperform X alone on M?",
                "method": "Run both on dataset D, compare metric M.",
                "expected_evidence": ["metrics.json"],
                "resource_limits": {"max_seconds": 3600},
                "stop_condition": "After one full run of both conditions.",
                "extensions": {},
            },
            "created_at": "2026-08-04T10:00:00Z",
            "updated_at": "2026-08-04T10:00:00Z",
            "extensions": {},
        }
        result = ds_lite_factor_card_v2.validate_factor_card_v2(card)
        self.assertEqual(result["factor_card_id"], "fc-001")

    def test_invalid_schema_version_rejected(self):
        card = {"schema_version": "wrong", "factor_card_id": "x"}
        with self.assertRaises(ds_lite_factor_card_v2.FactorCardError):
            ds_lite_factor_card_v2.validate_factor_card_v2(card)

    def test_derived_lineage_requires_parent_refs(self):
        card = {
            "schema_version": "ds-lite.factor-card.v2",
            "factor_card_id": "fc-002",
            "work_unit_id": "wu-002",
            "profile_id": "prof-002",
            "subject_ref": "ref",
            "status": "draft",
            "decision": "park",
            "factors": [],
            "lineage": {"source_type": "derived", "parent_refs": []},
            "differentiation_axes": [],
            "recent_work": [],
            "falsification_predictions": [{"prediction": "p", "falsifier": "f", "expected_outcome": "confirmed"}],
            "signal_refs": [],
            "selection_rationale": "",
            "minimal_test": {"question": "q", "method": "m", "expected_evidence": ["e"], "resource_limits": {}, "stop_condition": "s", "extensions": {}},
            "created_at": "2026-08-04T10:00:00Z",
            "updated_at": "2026-08-04T10:00:00Z",
            "extensions": {},
        }
        with self.assertRaises(ds_lite_factor_card_v2.FactorCardError):
            ds_lite_factor_card_v2.validate_factor_card_v2(card)


if __name__ == "__main__":
    unittest.main()
