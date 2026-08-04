#!/usr/bin/env python3
"""Tests for OpenScience File/CLI Bridge (PR 6)."""

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from plugins.deepscientist_lite_import_shim import ds_lite_openscience_bridge as bridge


class CapabilityManifestTests(unittest.TestCase):
    def test_export_manifest(self):
        """Should export a valid capability manifest."""
        project = {
            "project_id": "project-001",
            "capabilities": ["task-assessment", "experiment-execution"],
        }
        manifest = bridge.export_capability_manifest(project)
        self.assertEqual(manifest["project_id"], "project-001")
        self.assertEqual(manifest["status"], "active")
        self.assertIn("manifest_id", manifest)
        self.assertIn("constraints", manifest)

    def test_manifest_has_supported_protocols(self):
        """Manifest should list supported protocols."""
        project = {"project_id": "project-002"}
        manifest = bridge.export_capability_manifest(project)
        self.assertIsInstance(manifest["supported_protocols"], list)
        self.assertGreater(len(manifest["supported_protocols"]), 0)

    def test_invalid_project_id_rejected(self):
        """Invalid project_id should be rejected."""
        project = {"project_id": "invalid project id with spaces"}
        with self.assertRaises(bridge.BridgeError):
            bridge.export_capability_manifest(project)


class MissionOrderImportTests(unittest.TestCase):
    def _make_valid_order(self, mission_id="mission-001"):
        return {
            "mission_id": mission_id,
            "objective": "Determine if X improves Y.",
            "authority_digest": "sha256:abc123",
        }

    def _make_valid_project(self):
        return {
            "project_id": "project-001",
            "_existing_missions": {},
        }

    def test_import_order_creates_new_work_unit(self):
        """Importing a new order should create a new work unit."""
        order = self._make_valid_order()
        project = self._make_valid_project()
        result = bridge.import_order(order, project)
        self.assertTrue(result["created_new_work_unit"])
        self.assertEqual(result["import_status"], "received")
        self.assertEqual(result["mission_id"], "mission-001")

    def test_duplicate_delivery_is_idempotent(self):
        """Duplicate delivery should be idempotent."""
        order = self._make_valid_order()
        project = self._make_valid_project()

        # First delivery
        first = bridge.import_order(order, project)
        self.assertTrue(first["created_new_work_unit"])

        # Simulate the first delivery being stored
        project["_existing_missions"][first["mission_id"]] = first

        # Second delivery (duplicate)
        second = bridge.import_order(order, project)
        self.assertFalse(second["created_new_work_unit"])
        self.assertEqual(second["import_status"], "idempotent_duplicate")
        self.assertEqual(first["mission_id"], second["mission_id"])

    def test_missing_required_fields_rejected(self):
        """Order missing required fields should be rejected."""
        order = {"mission_id": "mission-002"}  # Missing objective and authority_digest
        project = self._make_valid_project()
        with self.assertRaises(bridge.BridgeError):
            bridge.import_order(order, project)


class MissionReturnExportTests(unittest.TestCase):
    def _make_valid_mission(self):
        return {"mission_id": "mission-001"}

    def _make_valid_evidence(self):
        return {
            "has_success": True,
            "has_failure": False,
            "has_blocker": False,
            "total_evidence": 5,
            "passed_checks": 5,
            "failed_checks": 0,
            "limitations": ["Limited to dataset D"],
            "next_decisions": ["Consider expanding to dataset E"],
        }

    def test_export_return_success(self):
        """Should export a success return pack."""
        mission = self._make_valid_mission()
        evidence = self._make_valid_evidence()
        return_pack = bridge.export_return(mission, evidence)
        self.assertEqual(return_pack["return_status"], "success")
        self.assertIn("return_digest", return_pack)
        self.assertEqual(return_pack["mission_id"], "mission-001")

    def test_export_return_blocked(self):
        """Should export a blocked return pack."""
        mission = self._make_valid_mission()
        evidence = self._make_valid_evidence()
        evidence["has_blocker"] = True
        return_pack = bridge.export_return(mission, evidence)
        self.assertEqual(return_pack["return_status"], "blocked")

    def test_export_return_partial(self):
        """Should export a partial return pack."""
        mission = self._make_valid_mission()
        evidence = self._make_valid_evidence()
        evidence["has_failure"] = True
        return_pack = bridge.export_return(mission, evidence)
        self.assertEqual(return_pack["return_status"], "partial")

    def test_return_pack_has_limitations_and_next_decisions(self):
        """Return pack should include limitations and next decisions."""
        mission = self._make_valid_mission()
        evidence = self._make_valid_evidence()
        return_pack = bridge.export_return(mission, evidence)
        self.assertEqual(len(return_pack["limitations"]), 1)
        self.assertEqual(len(return_pack["next_decisions"]), 1)


class BridgeConfigValidationTests(unittest.TestCase):
    def test_valid_config_passes(self):
        """A valid bridge config should pass validation."""
        config = {
            "shared_database": False,
            "daemon_enabled": False,
            "a2a_network_service": False,
            "standalone_fallback": True,
        }
        result = bridge.validate_bridge_config(config)
        self.assertEqual(result["verdict"], "pass")

    def test_shared_database_blocked(self):
        """Shared database should be blocked."""
        config = {
            "shared_database": True,
            "daemon_enabled": False,
            "a2a_network_service": False,
            "standalone_fallback": True,
        }
        result = bridge.validate_bridge_config(config)
        self.assertEqual(result["verdict"], "blocked")
        self.assertIn("shared_database_detected", result["rule_ids"])

    def test_daemon_blocked(self):
        """Daemon should be blocked."""
        config = {
            "shared_database": False,
            "daemon_enabled": True,
            "a2a_network_service": False,
            "standalone_fallback": True,
        }
        result = bridge.validate_bridge_config(config)
        self.assertEqual(result["verdict"], "blocked")

    def test_no_standalone_fallback_blocked(self):
        """Missing standalone fallback should be blocked."""
        config = {
            "shared_database": False,
            "daemon_enabled": False,
            "a2a_network_service": False,
            "standalone_fallback": False,
        }
        result = bridge.validate_bridge_config(config)
        self.assertEqual(result["verdict"], "blocked")
        self.assertIn("standalone_fallback_missing", result["rule_ids"])


if __name__ == "__main__":
    unittest.main()