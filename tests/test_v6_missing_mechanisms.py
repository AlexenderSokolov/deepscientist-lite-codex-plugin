#!/usr/bin/env python3
"""Tests for M04 Memory Layers, M05 Memory Card v2, M09 Task Router,
M13 Operator Levels, M22 Method Fidelity Manifest."""

import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from plugins.deepscientist_lite_import_shim import ds_lite_memory_layers
from plugins.deepscientist_lite_import_shim import ds_lite_memory_card_v2
from plugins.deepscientist_lite_import_shim import ds_lite_task_router
from plugins.deepscientist_lite_import_shim import ds_lite_operator_levels
from plugins.deepscientist_lite_import_shim import ds_lite_method_fidelity


class MemoryLayersTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()

    def test_create_layer_m0(self):
        result = ds_lite_memory_layers.create_memory_layer(self.root, "M0")
        self.assertEqual(result["layer"], "M0")
        self.assertEqual(result["write_permission"], "human")

    def test_create_layer_m4(self):
        result = ds_lite_memory_layers.create_memory_layer(self.root, "M4")
        self.assertEqual(result["layer"], "M4")

    def test_record_entry_m0(self):
        ds_lite_memory_layers.create_memory_layer(self.root, "M0")
        layer_path = str(Path(self.root) / "research" / "memory" / "M0-project-stable-goals.json")
        entry = {
            "entry_id": "goal-001",
            "entry_type": "goal",
            "statement": "Determine if X improves Y.",
            "status": "active",
            "created_at": "2026-08-04T10:00:00Z",
        }
        result = ds_lite_memory_layers.record_memory_entry(layer_path, entry)
        self.assertEqual(result["entry_id"], "goal-001")

    def test_entry_type_not_allowed_in_layer(self):
        ds_lite_memory_layers.create_memory_layer(self.root, "M0")
        layer_path = str(Path(self.root) / "research" / "memory" / "M0-project-stable-goals.json")
        entry = {
            "entry_id": "lesson-001",
            "entry_type": "lesson",
            "statement": "Always check dependencies.",
            "status": "active",
            "created_at": "2026-08-04T10:00:00Z",
        }
        with self.assertRaises(ds_lite_memory_layers.MemoryLayerError):
            ds_lite_memory_layers.record_memory_entry(layer_path, entry)

    def test_m4_experience_cannot_auto_promote_to_m0(self):
        entry = {
            "entry_id": "lesson-001",
            "entry_type": "lesson",
            "statement": "Always check dependencies.",
            "status": "active",
        }
        result = ds_lite_memory_layers.promote_memory("M4", "M0", entry)
        self.assertEqual(result["verdict"], "blocked")
        self.assertIn("m4_experience_cannot_auto_promote_to_m0", result["rule_ids"])

    def test_downward_promotion_not_allowed(self):
        entry = {
            "entry_id": "goal-001",
            "entry_type": "goal",
            "statement": "Test goal.",
            "status": "active",
        }
        result = ds_lite_memory_layers.promote_memory("M3", "M1", entry)
        self.assertEqual(result["verdict"], "blocked")
        self.assertIn("downward_promotion_not_allowed", result["rule_ids"])

    def test_layer_digest_stable(self):
        ds_lite_memory_layers.create_memory_layer(self.root, "M0")
        layer_path = str(Path(self.root) / "research" / "memory" / "M0-project-stable-goals.json")
        entry = {
            "entry_id": "goal-001",
            "entry_type": "goal",
            "statement": "Test goal.",
            "status": "active",
            "created_at": "2026-08-04T10:00:00Z",
        }
        ds_lite_memory_layers.record_memory_entry(layer_path, entry)
        digest1 = ds_lite_memory_layers.get_layer_digest(layer_path)
        digest2 = ds_lite_memory_layers.get_layer_digest(layer_path)
        self.assertEqual(digest1, digest2)


class MemoryCardV2Tests(unittest.TestCase):
    def test_create_and_validate(self):
        card = ds_lite_memory_card_v2.create_memory_card(
            card_id="mc-001",
            work_unit_id="wu-001",
            layer="M0",
            facts=["The dataset has 1000 samples."],
            decisions=["Use accuracy as the primary metric."],
            uncertainties=["Generalizability to other datasets is unknown."],
        )
        result = ds_lite_memory_card_v2.validate_memory_card_v2(card)
        self.assertEqual(result["verdict"], "pass")
        self.assertIn("card_digest", result)

    def test_invalid_layer_rejected(self):
        with self.assertRaises(ds_lite_memory_card_v2.MemoryCardError):
            ds_lite_memory_card_v2.create_memory_card(
                card_id="mc-002",
                work_unit_id="wu-002",
                layer="INVALID",
                facts=[],
                decisions=[],
            )

    def test_supersede(self):
        result = ds_lite_memory_card_v2.supersede_memory_card("mc-001", "mc-002")
        self.assertEqual(result["supersede_status"], "superseded")
        self.assertEqual(result["old_card_id"], "mc-001")
        self.assertEqual(result["new_card_id"], "mc-002")


class TaskRouterTests(unittest.TestCase):
    def test_route_diagnostic(self):
        route = ds_lite_task_router.route_task("diagnostic")
        self.assertEqual(route["task_kind"], "diagnostic")
        self.assertIn("ds-lite-intake", route["skills"])
        self.assertIn("ds-lite-scout", route["skills"])

    def test_route_confirmatory_includes_analysis_write(self):
        route = ds_lite_task_router.route_task("confirmatory")
        self.assertIn("ds-lite-analysis-write", route["skills"])

    def test_route_with_context_adds_skills(self):
        route = ds_lite_task_router.route_task("pilot", {"needs_writing": True, "needs_iteration": True})
        self.assertIn("ds-lite-analysis-write", route["skills"])
        self.assertIn("ds-lite-iterate", route["skills"])

    def test_select_minimal_sufficient_combination(self):
        route = ds_lite_task_router.route_task("diagnostic")
        available = ["ds-lite-intake", "ds-lite-scout", "ds-lite-experiment", "ds-lite-review"]
        result = ds_lite_task_router.select_minimal_sufficient_combination(route, available)
        self.assertTrue(result["is_sufficient"])
        self.assertEqual(result["missing_skills"], [])

    def test_select_with_missing_skills(self):
        route = ds_lite_task_router.route_task("diagnostic")
        available = ["ds-lite-intake", "ds-lite-scout"]
        result = ds_lite_task_router.select_minimal_sufficient_combination(route, available)
        self.assertFalse(result["is_sufficient"])
        self.assertGreater(len(result["missing_skills"]), 0)

    def test_validate_task_route(self):
        route = ds_lite_task_router.route_task("engineering")
        result = ds_lite_task_router.validate_task_route(route)
        self.assertEqual(result["verdict"], "pass")

    def test_invalid_task_kind_rejected(self):
        with self.assertRaises(ds_lite_task_router.TaskRouterError):
            ds_lite_task_router.route_task("invalid-kind")


class OperatorLevelsTests(unittest.TestCase):
    def test_validate_operator_action_o0(self):
        action = {
            "schema_version": "ds-lite.operator-levels.v1",
            "action_id": "action-001",
            "operator_level": "O0",
            "action_kind": "read-public",
            "target_identity": "https://example.com",
            "authorized_effect_class": "read-only",
            "payload_digest": "sha256:abc",
            "status": "planned",
            "created_at": "2026-08-04T10:00:00Z",
            "extensions": {},
        }
        result = ds_lite_operator_levels.validate_operator_action(action)
        self.assertEqual(result["verdict"], "pass")

    def test_check_permission_o0_no_auth_required(self):
        action = {"human_approved": False}
        result = ds_lite_operator_levels.check_operator_permission("O0", action)
        self.assertEqual(result["verdict"], "pass")
        self.assertEqual(result["authorization_required"], "none")

    def test_check_permission_o3_requires_human_approval(self):
        action = {"human_approved": False}
        result = ds_lite_operator_levels.check_operator_permission("O3", action)
        self.assertEqual(result["verdict"], "blocked")
        self.assertIn("human_approval_required", result["rule_ids"])

    def test_check_permission_o3_with_approval(self):
        action = {"human_approved": True}
        result = ds_lite_operator_levels.check_operator_permission("O3", action)
        self.assertEqual(result["verdict"], "pass")

    def test_create_operator_contract(self):
        contract = ds_lite_operator_levels.create_operator_contract(
            "O2",
            {"action_kind": "write-local"},
            {"target": "local-file.txt"},
        )
        self.assertEqual(contract["operator_level"], "O2")
        self.assertEqual(contract["authorization_required"], "explicit-contract")
        self.assertTrue(contract["is_reversible"])

    def test_invalid_level_rejected(self):
        with self.assertRaises(ds_lite_operator_levels.OperatorError):
            ds_lite_operator_levels.check_operator_permission("O9", {})


class MethodFidelityManifestTests(unittest.TestCase):
    def test_create_and_validate(self):
        manifest = ds_lite_method_fidelity.create_method_fidelity_manifest(
            method_id="method-001",
            method_name="Random Forest with SMOTE",
            original_method_ref="doi:10.1000/original",
            adaptations=[
                {"type": "parameter-change", "description": "Changed n_estimators from 100 to 200."},
            ],
            deletions=[
                {"type": "step-removed", "description": "Removed PCA preprocessing step."},
            ],
            actual_code_ref="research/code/experiment.py",
            code_identity_digest="sha256:abc123",
            fidelity_assessment={"fidelity_level": "medium", "major_deviations": ["Removed PCA"], "notes": "PCA removal may affect results."},
        )
        result = ds_lite_method_fidelity.validate_method_fidelity_manifest(manifest)
        self.assertEqual(result["verdict"], "pass")
        self.assertIn("fidelity_digest", result)

    def test_invalid_adaptation_type_rejected(self):
        manifest = ds_lite_method_fidelity.create_method_fidelity_manifest(
            method_id="method-002",
            method_name="Test Method",
            original_method_ref="ref",
            adaptations=[{"type": "invalid-type", "description": "Test"}],
            deletions=[],
            actual_code_ref="ref",
            code_identity_digest="sha256:abc",
        )
        with self.assertRaises(ds_lite_method_fidelity.FidelityError):
            ds_lite_method_fidelity.validate_method_fidelity_manifest(manifest)

    def test_check_code_identity_match(self):
        manifest = ds_lite_method_fidelity.create_method_fidelity_manifest(
            method_id="method-003",
            method_name="Test",
            original_method_ref="ref",
            adaptations=[],
            deletions=[],
            actual_code_ref="research/code/experiment.py",
            code_identity_digest="sha256:abc123",
        )
        result = ds_lite_method_fidelity.check_code_identity(manifest, "research/code/experiment.py")
        self.assertTrue(result["matches"])

    def test_check_code_identity_mismatch(self):
        manifest = ds_lite_method_fidelity.create_method_fidelity_manifest(
            method_id="method-004",
            method_name="Test",
            original_method_ref="ref",
            adaptations=[],
            deletions=[],
            actual_code_ref="research/code/original.py",
            code_identity_digest="sha256:abc123",
        )
        result = ds_lite_method_fidelity.check_code_identity(manifest, "research/code/modified.py")
        self.assertFalse(result["matches"])

    def test_fidelity_digest_stable(self):
        manifest1 = ds_lite_method_fidelity.create_method_fidelity_manifest(
            method_id="method-005",
            method_name="Test",
            original_method_ref="ref",
            adaptations=[],
            deletions=[],
            actual_code_ref="ref",
            code_identity_digest="sha256:abc",
        )
        manifest2 = ds_lite_method_fidelity.create_method_fidelity_manifest(
            method_id="method-005",
            method_name="Test",
            original_method_ref="ref",
            adaptations=[],
            deletions=[],
            actual_code_ref="ref",
            code_identity_digest="sha256:abc",
        )
        result1 = ds_lite_method_fidelity.validate_method_fidelity_manifest(manifest1)
        result2 = ds_lite_method_fidelity.validate_method_fidelity_manifest(manifest2)
        self.assertEqual(result1["fidelity_digest"], result2["fidelity_digest"])


if __name__ == "__main__":
    unittest.main()