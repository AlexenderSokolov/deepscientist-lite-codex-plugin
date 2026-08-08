#!/usr/bin/env python3
"""End-to-end fixture for the v6 signal/frontier/iteration/evidence/review path."""

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from plugins.deepscientist_lite_import_shim import (
    ds_lite_claim_ledger,
    ds_lite_frontier,
    ds_lite_signal_ledger,
)

ITERATION_PATH = ROOT / "plugins" / "deepscientist-lite-core" / "scripts" / "ds_lite_iteration.py"
if str(ITERATION_PATH.parent) not in sys.path:
    sys.path.insert(0, str(ITERATION_PATH.parent))
spec = importlib.util.spec_from_file_location("ds_lite_iteration_e2e", ITERATION_PATH)
assert spec and spec.loader
ds_lite_iteration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ds_lite_iteration)


class SignalFrontierClaimE2ETests(unittest.TestCase):
    def test_signal_to_reviewed_claim_and_frontier_is_non_authoritative(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifacts = root / "research" / "artifacts"
            evidence = root / "research" / "evidence" / "run-001"
            artifacts.mkdir(parents=True)
            evidence.mkdir(parents=True)

            signal_path = artifacts / "signal-ledger-wu-e2e.json"
            ds_lite_signal_ledger.create_ledger("wu-e2e", "wu-e2e", str(root))
            signal_path = artifacts / "signal-ledger-wu-e2e.json"
            ds_lite_signal_ledger.append_signal(str(signal_path), {
                "signal_id": "signal-001", "signal_type": "feasibility-probe",
                "source_ref": "research/notes/probe.md",
                "scope": {"work_unit_id": "wu-e2e", "route_node_id": "route-a"},
                "observation": "The bounded probe is executable.", "confidence": "medium",
                "dependencies": [], "expiry": {"type": "on-supersede"},
                "status": "active", "created_at": "2026-08-07T00:00:00Z", "extensions": {},
            })

            frontier_path = artifacts / "discovery-frontier-wu-e2e.json"
            ds_lite_frontier.create_frontier("wu-e2e", "wu-e2e", str(root))
            ds_lite_frontier.add_candidate(str(frontier_path), {
                "candidate_id": "candidate-001", "hypothesis": "Probe succeeds.",
                "mechanism": "bounded execution", "differentiation": "single-axis",
                "signal_refs": ["signal-001"], "factor_card_ref": "research/artifacts/factor-card-001.json",
                "status": "proposed", "selection_rationale": "", "falsification_prediction": {
                    "prediction": "Probe succeeds", "falsifier": "Probe fails"
                }, "minimal_test_ref": "research/evidence/run-001/contract.json", "extensions": {},
            })
            selected = ds_lite_frontier.select_candidate(str(frontier_path), "candidate-001", "fits budget")
            self.assertEqual(selected["status"], "selected")

            manifest = {
                "schema_version": "ds-lite.evidence.v1", "run_id": "run-001", "node_id": "node-001",
                "status": "verified", "files": [{"role": "metrics", "path": "metrics.json", "sha256": "0" * 64}],
                "verification": {"status": "pass"},
            }
            (evidence / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            iteration = {
                "schema_version": "ds-lite.iteration.v1", "iteration_id": "iteration-001", "work_unit_id": "wu-e2e",
                "profile_id": "core-planning", "execution_mode": "inline", "status": "completed",
                "selected_skill": "ds-lite-iterate", "expected_revision": 0, "before_revision": 0, "after_revision": 1,
                "action": {"kind": "review", "summary": "Review probe", "prediction": "supportable",
                            "falsification_condition": "failed probe", "resource_limits": [{"dimension": "actions", "unit": "count", "value": 1}],
                            "stop_condition": "stop after review", "extensions": {}},
                "input_refs": ["research/evidence/run-001/manifest.json", str(frontier_path.relative_to(root)).replace("\\", "/")],
                "output_refs": ["research/artifacts/review-001.json"],
                "graph_changes": [{"kind": "none", "subject_id": "candidate-001", "summary": "Projection only", "extensions": {}}],
                "validations": [{"command": "fixture", "status": "pass", "summary": "fixture", "extensions": {}}],
                "stop_reason": "action-completed", "reflection": {
                    "observed_outcomes": ["probe evidence recorded"], "hypothesis_updates": [{"hypothesis_id": "candidate-001", "status": "supported", "evidence_refs": ["research/evidence/run-001/manifest.json"], "summary": "reviewed", "extensions": {}}],
                    "expectation_gap": "none", "negative_results": [], "responsibility": {"authorization_basis": "fixture", "boundaries_respected": ["bounded"], "unresolved_obligations": [], "extensions": {}},
                    "learned_boundaries": ["frontier is non-authoritative"], "next_candidates": [], "minimal_discriminating_test": "none", "extensions": {},
                },
                "user_report": {"summary": "fixture", "files_changed": [], "validation_summary": "pass", "failure_layer": "none", "unverified": [], "hypothesis_changes": [], "next_action": "none", "decision_needed": "none", "extensions": {}},
                "started_at": "2026-08-07T00:00:00Z", "completed_at": "2026-08-07T00:01:00Z", "extensions": {"frontier_candidate": "candidate-001"},
            }
            self.assertEqual(ds_lite_iteration.validate_iteration(iteration)["status"], "completed")

            ledger_path = artifacts / "claim-ledger-wu-e2e.json"
            ds_lite_claim_ledger.create_ledger("wu-e2e", "wu-e2e", str(root))
            ds_lite_claim_ledger.append_claim(str(ledger_path), {
                "claim_id": "claim-001", "claim_type": "positive-result", "statement": "Probe succeeds.",
                "selector": {"type": "metric", "query": "status == verified"},
                "evidence_refs": ["research/evidence/run-001/manifest.json"], "dependence_group": "probe",
                "transformation_chain": [], "executed_code_ref": "tests/fixture.py", "verifier": {"type": "deterministic", "result": "pass"},
                "fidelity": "medium", "status": "draft", "created_at": "2026-08-07T00:00:00Z", "extensions": {},
            })
            review_path = artifacts / "review-001.json"
            review_path.write_text(json.dumps({
                "schema_version": "ds-lite.review-result.v1", "review_id": "review-001", "work_unit_id": "wu-e2e", "profile_id": "core-review",
                "review_node_id": "review-001", "reviewed_node_id": "iteration-001", "reviewed_evidence_refs": ["research/evidence/run-001/manifest.json"],
                "evidence_validator": "validator-001", "evidence_digest": "0" * 64, "verdict": "pass", "claim_assessment": "supportable",
                "channels": {"integrity": "pass"}, "limitations": [], "review_artifact_ref": "research/artifacts/review-001.json",
                "completed_at": "2026-08-07T00:02:00Z", "extensions": {"claim_id": "claim-001"},
            }), encoding="utf-8")
            promoted = ds_lite_claim_ledger.promote_claim_from_review(str(ledger_path), "claim-001", str(review_path))
            self.assertEqual(promoted["status"], "supported")
            self.assertNotIn("graph_route_active", ds_lite_frontier.project_frontier(str(frontier_path)))


if __name__ == "__main__":
    unittest.main()
