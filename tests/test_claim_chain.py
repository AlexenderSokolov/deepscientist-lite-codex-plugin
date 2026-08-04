#!/usr/bin/env python3
"""Tests for Chain of Evidence (PR 2)."""

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from plugins.deepscientist_lite_import_shim import ds_lite_claim_chain


class ChainOfEvidenceTests(unittest.TestCase):
    def _make_valid_claim(self):
        return {
            "claim_id": "claim-001",
            "selector": {
                "type": "file-range",
                "value": "results.json:lines[10-15]",
                "artifact_ref": "research/evidence/exp-001/results.json",
            },
            "transformation_chain": [
                {
                    "type": "aggregation",
                    "description": "Average accuracy across 5 folds",
                    "input_ref": "results.json:fold_*",
                    "output_ref": "results.json:avg_accuracy",
                },
            ],
            "evidence_refs": ["research/evidence/exp-001/results.json"],
            "dependence_group": "group-A",
            "executed_code_ref": "research/code/experiment.py:run()",
            "verifier": {
                "type": "deterministic",
                "result": "pass",
            },
        }

    def test_valid_claim_passes(self):
        claim = self._make_valid_claim()
        result = ds_lite_claim_chain.validate_chain_of_evidence(claim)
        self.assertEqual(result["verdict"], "pass")
        self.assertIn("chain_digest", result)

    def test_claim_without_selector_is_blocked(self):
        claim = self._make_valid_claim()
        claim["selector"] = {}
        result = ds_lite_claim_chain.validate_chain_of_evidence(claim)
        self.assertEqual(result["verdict"], "blocked")
        self.assertIn("missing_or_invalid_selector", result["rule_ids"])

    def test_missing_evidence_refs_is_blocked(self):
        claim = self._make_valid_claim()
        claim["evidence_refs"] = []
        result = ds_lite_claim_chain.validate_chain_of_evidence(claim)
        self.assertEqual(result["verdict"], "blocked")
        self.assertIn("missing_evidence_refs", result["rule_ids"])

    def test_missing_executed_code_ref_is_blocked(self):
        claim = self._make_valid_claim()
        claim["executed_code_ref"] = ""
        result = ds_lite_claim_chain.validate_chain_of_evidence(claim)
        self.assertEqual(result["verdict"], "blocked")
        self.assertIn("missing_executed_code_ref", result["rule_ids"])

    def test_missing_verifier_is_blocked(self):
        claim = self._make_valid_claim()
        claim["verifier"] = {}
        result = ds_lite_claim_chain.validate_chain_of_evidence(claim)
        self.assertEqual(result["verdict"], "blocked")
        self.assertIn("missing_verifier", result["rule_ids"])

    def test_missing_dependence_group_is_blocked(self):
        claim = self._make_valid_claim()
        claim["dependence_group"] = ""
        result = ds_lite_claim_chain.validate_chain_of_evidence(claim)
        self.assertEqual(result["verdict"], "blocked")
        self.assertIn("missing_dependence_group", result["rule_ids"])

    def test_empty_transformation_chain_triggers_warning(self):
        claim = self._make_valid_claim()
        claim["transformation_chain"] = []
        result = ds_lite_claim_chain.validate_chain_of_evidence(claim)
        self.assertIn("empty_transformation_chain", result["rule_ids"])
        self.assertIn(result["verdict"], {"warning", "blocked"})

    def test_shared_dependency_detected(self):
        claims = [
            {"claim_id": "c1", "dependence_group": "shared"},
            {"claim_id": "c2", "dependence_group": "shared"},
            {"claim_id": "c3", "dependence_group": "independent"},
        ]
        audit = ds_lite_claim_chain.check_dependency_group(claims)
        self.assertTrue(audit["has_shared_dependency"])
        self.assertEqual(audit["shared_count"], 2)
        self.assertEqual(audit["independent_count"], 1)

    def test_no_shared_dependency(self):
        claims = [
            {"claim_id": "c1", "dependence_group": "g1"},
            {"claim_id": "c2", "dependence_group": "g2"},
        ]
        audit = ds_lite_claim_chain.check_dependency_group(claims)
        self.assertFalse(audit["has_shared_dependency"])

    def test_chain_digest_is_stable(self):
        claim1 = self._make_valid_claim()
        claim2 = self._make_valid_claim()
        result1 = ds_lite_claim_chain.validate_chain_of_evidence(claim1)
        result2 = ds_lite_claim_chain.validate_chain_of_evidence(claim2)
        self.assertEqual(result1["chain_digest"], result2["chain_digest"])

    def test_validate_claim_ledger(self):
        ledger = {
            "schema_version": "ds-lite.claim-ledger.v1",
            "ledger_id": "ledger-001",
            "claims": [self._make_valid_claim()],
        }
        result = ds_lite_claim_chain.validate_claim_ledger(ledger)
        self.assertIn(result["verdict"], {"pass", "warning"})
        self.assertIn("ledger_digest", result)

    def test_create_chain_entry(self):
        entry = ds_lite_claim_chain.create_chain_entry(
            claim_id="claim-002",
            selector_type="json-path",
            selector_value="$.results.accuracy",
            artifact_ref="results.json",
            transformation_chain=[
                {"type": "identity", "description": "Direct read", "input_ref": "r", "output_ref": "o"},
            ],
            evidence_refs=["results.json"],
            dependence_group="group-B",
            executed_code_ref="script.py",
            verifier_type="deterministic",
            verifier_result="pass",
        )
        self.assertEqual(entry["claim_id"], "claim-002")
        self.assertEqual(entry["selector"]["type"], "json-path")


if __name__ == "__main__":
    unittest.main()