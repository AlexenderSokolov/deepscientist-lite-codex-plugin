#!/usr/bin/env python3
"""Tests for Mission Handoff Quality Protocol (PR 4)."""

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from plugins.deepscientist_lite_import_shim import ds_lite_handoff_quality as hq


class MissionOrderTests(unittest.TestCase):
    def _make_valid_mission(self):
        return hq.create_mission_order(
            mission_id="mission-001",
            project_id="project-001",
            objective="Determine if X improves Y.",
            non_goals=["Cannot claim generalizability."],
            owner_id="owner-001",
            budget={"max_tokens": 10000},
            acceptance_criteria=[{"metric": "accuracy", "threshold": 0.85}],
            stop_conditions=["After one full run."],
            authority_digest="sha256:abc123",
        )

    def test_valid_mission_passes(self):
        mission = self._make_valid_mission()
        result = hq.validate_mission_order(mission)
        self.assertEqual(result["verdict"], "pass")

    def test_empty_objective_is_blocked(self):
        mission = self._make_valid_mission()
        mission["objective"] = ""
        result = hq.validate_mission_order(mission)
        self.assertEqual(result["verdict"], "blocked")
        self.assertIn("empty_objective", result["rule_ids"])

    def test_empty_acceptance_criteria_is_blocked(self):
        mission = self._make_valid_mission()
        mission["acceptance_criteria"] = []
        result = hq.validate_mission_order(mission)
        self.assertEqual(result["verdict"], "blocked")

    def test_empty_stop_conditions_is_blocked(self):
        mission = self._make_valid_mission()
        mission["stop_conditions"] = []
        result = hq.validate_mission_order(mission)
        self.assertEqual(result["verdict"], "blocked")

    def test_missing_authority_digest_is_blocked(self):
        mission = self._make_valid_mission()
        mission["authority_digest"] = ""
        result = hq.validate_mission_order(mission)
        self.assertEqual(result["verdict"], "blocked")


class HandoffPhaseTests(unittest.TestCase):
    def _make_mission_with_status(self, status):
        mission = {
            "schema_version": "ds-lite.mission-handoff-quality.v1",
            "mission_id": "mission-002",
            "status": status,
        }
        return mission

    def test_returned_not_equal_integrated(self):
        """returned -> integrate is the correct transition."""
        mission = self._make_mission_with_status("returned")
        result = hq.validate_handoff_phase(mission, "integrate")
        self.assertEqual(result["verdict"], "pass")

    def test_cannot_close_without_integration(self):
        mission = self._make_mission_with_status("returned")
        result = hq.validate_handoff_phase(mission, "close")
        self.assertEqual(result["verdict"], "blocked")
        self.assertIn("cannot_close_without_integration", result["rule_ids"])

    def test_cannot_execute_without_acceptance(self):
        mission = self._make_mission_with_status("offered")
        result = hq.validate_handoff_phase(mission, "execute")
        self.assertEqual(result["verdict"], "blocked")
        self.assertIn("cannot_execute_without_acceptance", result["rule_ids"])

    def test_cannot_return_without_execution(self):
        mission = self._make_mission_with_status("accepted")
        result = hq.validate_handoff_phase(mission, "return")
        self.assertEqual(result["verdict"], "blocked")
        self.assertIn("cannot_return_without_execution", result["rule_ids"])

    def test_cannot_integrate_without_return(self):
        mission = self._make_mission_with_status("executing")
        result = hq.validate_handoff_phase(mission, "integrate")
        self.assertEqual(result["verdict"], "blocked")
        self.assertIn("cannot_integrate_without_return", result["rule_ids"])

    def test_rejected_mission_cannot_proceed(self):
        mission = self._make_mission_with_status("rejected")
        result = hq.validate_handoff_phase(mission, "execute")
        self.assertEqual(result["verdict"], "blocked")
        self.assertIn("rejected_mission_cannot_proceed", result["rule_ids"])


class QualityContractTests(unittest.TestCase):
    def _make_valid_quality_contract(self):
        return {
            "schema_version": "ds-lite.mission-handoff-quality.v1",
            "gates": {
                "G0-identity": "pass",
                "G1-requirements": "pass",
                "G2-security-privacy": "pass",
                "G3-license-supply-chain": "pass",
                "G4-engineering-quality": "pass",
                "G5-scientific-method": "pass",
                "G6-release-readiness": "pass",
            },
            "risk_level": "Q2",
        }

    def test_valid_quality_contract_passes(self):
        contract = self._make_valid_quality_contract()
        result = hq.validate_quality_contract(contract)
        self.assertEqual(result["verdict"], "pass")

    def test_unknown_gate_not_aggregated_to_pass(self):
        contract = self._make_valid_quality_contract()
        contract["gates"]["G0-identity"] = "unknown"
        result = hq.validate_quality_contract(contract)
        self.assertEqual(result["verdict"], "blocked")
        self.assertIn("gate_G0-identity_not_resolved", result["rule_ids"])

    def test_not_run_gate_is_blocked(self):
        contract = self._make_valid_quality_contract()
        contract["gates"]["G5-scientific-method"] = "not-run"
        result = hq.validate_quality_contract(contract)
        self.assertEqual(result["verdict"], "blocked")

    def test_failed_gate_is_blocked(self):
        contract = self._make_valid_quality_contract()
        contract["gates"]["G4-engineering-quality"] = "fail"
        result = hq.validate_quality_contract(contract)
        self.assertEqual(result["verdict"], "blocked")

    def test_missing_gates_are_blocked(self):
        contract = self._make_valid_quality_contract()
        del contract["gates"]["G6-release-readiness"]
        result = hq.validate_quality_contract(contract)
        self.assertEqual(result["verdict"], "blocked")

    def test_unknown_gate_id_is_blocked(self):
        contract = self._make_valid_quality_contract()
        contract["gates"]["G7-unknown"] = "pass"
        result = hq.validate_quality_contract(contract)
        self.assertEqual(result["verdict"], "blocked")


class ReviewPackageTests(unittest.TestCase):
    def test_create_review_package_with_blocker(self):
        findings = [
            {"finding_id": "f1", "severity": "blocker", "status": "open", "description": "Critical issue"},
            {"finding_id": "f2", "severity": "minor", "status": "open", "description": "Minor issue"},
        ]
        package = hq.create_review_package(findings)
        self.assertEqual(package["aggregation"]["overall_verdict"], "blocked")
        self.assertEqual(package["aggregation"]["total_findings"], 2)

    def test_create_review_package_passes(self):
        findings = [
            {"finding_id": "f1", "severity": "minor", "status": "addressed", "description": "Fixed"},
        ]
        package = hq.create_review_package(findings)
        self.assertEqual(package["aggregation"]["overall_verdict"], "pass")

    def test_review_package_preserves_disagreements(self):
        findings = [
            {"finding_id": "f1", "severity": "major", "status": "open", "description": "Disagreement 1"},
            {"finding_id": "f2", "severity": "major", "status": "wont-fix", "description": "Disagreement 2"},
            {"finding_id": "f3", "severity": "info", "status": "false-positive", "description": "Not an issue"},
        ]
        package = hq.create_review_package(findings)
        self.assertEqual(package["aggregation"]["status_counts"]["wont-fix"], 1)
        self.assertEqual(package["aggregation"]["status_counts"]["false-positive"], 1)
        self.assertEqual(package["aggregation"]["status_counts"]["open"], 1)

    def test_invalid_findings_are_filtered(self):
        findings = [
            {"finding_id": "f1", "severity": "invalid", "status": "open"},
            {"finding_id": "", "severity": "minor", "status": "open"},
            "not-a-dict",
        ]
        package = hq.create_review_package(findings)
        self.assertEqual(package["aggregation"]["total_findings"], 0)


if __name__ == "__main__":
    unittest.main()