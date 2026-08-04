#!/usr/bin/env python3
"""Tests for Experiment Contract v2 (PR 1)."""

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from plugins.deepscientist_lite_import_shim import ds_lite_contract_v2


class ExperimentContractV2Tests(unittest.TestCase):
    def _make_valid_contract(self):
        return ds_lite_contract_v2.create_contract(
            contract_id="contract-001",
            work_unit_id="wu-001",
            mission_ref="mission:example@1",
            objective="Determine if X improves Y on dataset D.",
            non_goals=["Cannot claim generalizability beyond D."],
            input_snapshot={"dataset": "D v1.0", "code": "commit-abc123"},
            owner_id="owner-001",
            budget={"max_tokens": 10000, "max_seconds": 3600},
            acceptance_criteria=[
                {"metric": "accuracy", "direction": "higher", "threshold": 0.85},
            ],
            task_assessment_ref="assessment-001",
            fidelity_level="L3-pilot",
            comparison_domain="same-dataset",
            role_status="protected",
            evaluator={"type": "deterministic", "name": "accuracy_evaluator"},
            baseline={"name": "baseline-v1", "metric": "accuracy", "value": 0.80},
            stop_conditions=["After one full run of both conditions."],
        )

    def test_valid_contract_passes(self):
        contract = self._make_valid_contract()
        result = ds_lite_contract_v2.validate_experiment_contract_v2(contract)
        self.assertEqual(result["verdict"], "pass")
        self.assertIn("contract_digest", result)

    def test_missing_task_assessment_is_blocked(self):
        contract = self._make_valid_contract()
        contract["task_assessment_ref"] = ""
        result = ds_lite_contract_v2.validate_experiment_contract_v2(contract)
        self.assertEqual(result["verdict"], "blocked")
        self.assertIn("missing_task_assessment", result["rule_ids"])

    def test_contaminated_role_is_blocked(self):
        contract = self._make_valid_contract()
        contract["role_status"] = "contaminated"
        result = ds_lite_contract_v2.validate_experiment_contract_v2(contract)
        self.assertEqual(result["verdict"], "blocked")
        self.assertIn("contaminated_role", result["rule_ids"])

    def test_confirmatory_requires_protected_role(self):
        contract = self._make_valid_contract()
        contract["fidelity_level"] = "L4-confirmatory"
        contract["role_status"] = "open"
        result = ds_lite_contract_v2.validate_experiment_contract_v2(contract)
        self.assertEqual(result["verdict"], "blocked")
        self.assertIn("confirmatory_requires_protected_role", result["rule_ids"])

    def test_empty_stop_conditions_is_blocked(self):
        contract = self._make_valid_contract()
        contract["stop_conditions"] = []
        result = ds_lite_contract_v2.validate_experiment_contract_v2(contract)
        self.assertEqual(result["verdict"], "blocked")
        self.assertIn("empty_stop_conditions", result["rule_ids"])

    def test_missing_evaluator_is_blocked(self):
        contract = self._make_valid_contract()
        contract["evaluator"] = {}
        result = ds_lite_contract_v2.validate_experiment_contract_v2(contract)
        self.assertEqual(result["verdict"], "blocked")
        self.assertIn("missing_evaluator", result["rule_ids"])

    def test_missing_baseline_for_comparison_is_blocked(self):
        contract = self._make_valid_contract()
        contract["baseline"] = {}
        result = ds_lite_contract_v2.validate_experiment_contract_v2(contract)
        self.assertEqual(result["verdict"], "blocked")
        self.assertIn("missing_baseline_for_comparison", result["rule_ids"])

    def test_missing_budget_limit_triggers_warning(self):
        contract = self._make_valid_contract()
        contract["budget"] = {"description": "No explicit limit"}
        result = ds_lite_contract_v2.validate_experiment_contract_v2(contract)
        self.assertIn("missing_budget_limit", result["rule_ids"])

    def test_contract_digest_is_stable(self):
        contract1 = self._make_valid_contract()
        contract2 = self._make_valid_contract()
        result1 = ds_lite_contract_v2.validate_experiment_contract_v2(contract1)
        result2 = ds_lite_contract_v2.validate_experiment_contract_v2(contract2)
        self.assertEqual(result1["contract_digest"], result2["contract_digest"])

    def test_revision_must_increase(self):
        base = self._make_valid_contract()
        base["revision"] = 3
        candidate = self._make_valid_contract()
        candidate["revision"] = 2
        result = ds_lite_contract_v2.validate_contract_revision(base, candidate)
        self.assertEqual(result["verdict"], "blocked")
        self.assertIn("revision_must_increase", result["rule_ids"])

    def test_metric_change_requires_new_revision(self):
        base = self._make_valid_contract()
        base["revision"] = 3
        candidate = self._make_valid_contract()
        candidate["revision"] = 3
        candidate["acceptance_criteria"] = [
            {"metric": "accuracy", "direction": "higher", "threshold": 0.90},
        ]
        result = ds_lite_contract_v2.validate_contract_revision(base, candidate)
        self.assertEqual(result["verdict"], "blocked")
        self.assertEqual(result["domain_status"], "protocol_authority_conflict")

    def test_read_v1_contract(self):
        v1_doc = {
            "contract_id": "old-contract",
            "objective": "Old objective",
            "non_goals": ["Old non-goal"],
            "budget": {"max_seconds": 60},
            "acceptance_criteria": [{"metric": "accuracy", "threshold": 0.8}],
            "status": "completed",
            "revision": 1,
            "extra_field": "should be preserved",
        }
        legacy = ds_lite_contract_v2.read_v1_contract(v1_doc)
        self.assertEqual(legacy["contract_id"], "old-contract")
        self.assertEqual(legacy["schema_version"], "ds-lite.experiment-contract.v1-legacy")
        self.assertEqual(legacy["legacy_fields"]["extra_field"], "should be preserved")

    def test_invalid_schema_version_rejected(self):
        contract = {"schema_version": "wrong", "contract_id": "x"}
        with self.assertRaises(ds_lite_contract_v2.ContractError):
            ds_lite_contract_v2.validate_experiment_contract_v2(contract)


if __name__ == "__main__":
    unittest.main()