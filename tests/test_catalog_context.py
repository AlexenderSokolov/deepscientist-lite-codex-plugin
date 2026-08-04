#!/usr/bin/env python3
"""Tests for Catalog, Context, Experience, and Skill Admission (PR 5)."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from plugins.deepscientist_lite_import_shim import ds_lite_catalog
from plugins.deepscientist_lite_import_shim import ds_lite_experience_ledger
from plugins.deepscientist_lite_import_shim import ds_lite_skill_admission


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        # Create some test files
        (Path(self.root) / "src").mkdir()
        (Path(self.root) / "src" / "main.py").write_text("print('hello')")
        (Path(self.root) / "README.md").write_text("# Test Project")
        (Path(self.root) / "__pycache__").mkdir()
        (Path(self.root) / "__pycache__" / "main.cpython-311.pyc").write_text("cached")

    def test_catalog_rebuildable(self):
        """Catalog rebuild should produce the same digest."""
        cat1 = ds_lite_catalog.build_catalog(self.root)
        cat2 = ds_lite_catalog.build_catalog(self.root)
        self.assertEqual(cat1["catalog_digest"], cat2["catalog_digest"])

    def test_catalog_skips_pycache(self):
        """Catalog should skip __pycache__ directories."""
        catalog = ds_lite_catalog.build_catalog(self.root)
        paths = [e["path"] for e in catalog["entries"]]
        self.assertNotIn("__pycache__/main.cpython-311.pyc", paths)

    def test_catalog_includes_source_files(self):
        """Catalog should include .py and .md files."""
        catalog = ds_lite_catalog.build_catalog(self.root)
        paths = [e["path"] for e in catalog["entries"]]
        self.assertIn("src/main.py", paths)
        self.assertIn("README.md", paths)

    def test_context_within_token_budget(self):
        """Context receipt should stay within token budget."""
        catalog = ds_lite_catalog.build_catalog(self.root)
        scope = {
            "include_patterns": [".py", ".md"],
            "exclude_patterns": [],
            "priority_files": [],
            "max_file_tokens": 100,
        }
        receipt = ds_lite_catalog.compile_context(catalog, scope, token_budget=4000)
        self.assertLessEqual(receipt["estimated_tokens"], 4000)
        self.assertGreater(receipt["included_count"], 0)

    def test_context_receipt_has_exclusions(self):
        """Context receipt should record what was excluded and why."""
        catalog = ds_lite_catalog.build_catalog(self.root)
        scope = {
            "include_patterns": [".py"],
            "exclude_patterns": [],
            "priority_files": [],
            "max_file_tokens": 100,
        }
        receipt = ds_lite_catalog.compile_context(catalog, scope, token_budget=4000)
        # README.md should be excluded because it doesn't match .py
        excluded_paths = [e["path"] for e in receipt["excluded"]]
        self.assertIn("README.md", excluded_paths)


class ExperienceLedgerTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.ledger_path = str(Path(self.root) / "research" / "artifacts" / "experience-ledger-test.json")

    def test_create_and_append_entry(self):
        """Experience ledger should create and append entries."""
        ds_lite_experience_ledger.create_ledger("test", "project-001", self.root)
        entry = ds_lite_experience_ledger.record_experience(
            experience_type="incident",
            title="Test failure",
            description="Test failed due to missing dependency",
            trigger_conditions=["Running test suite"],
            evidence_refs=["logs/test.log"],
            extensions={"severity": "major"},
        )
        result = ds_lite_experience_ledger.append_entry(self.ledger_path, entry)
        self.assertEqual(result["experience_type"], "incident")
        self.assertIn("entry_digest", result)

    def test_experience_does_not_auto_modify_skill(self):
        """Skill change proposal must be pending_review and auto_apply=False."""
        lesson = ds_lite_experience_ledger.record_experience(
            experience_type="lesson",
            title="Always check dependencies",
            description="Missing dependencies caused test failure",
            extensions={},
        )
        proposal = ds_lite_experience_ledger.propose_skill_change(
            lesson_entry=lesson,
            proposed_change="Add dependency check to pre-test script",
            rationale="Prevents test failures from missing dependencies",
        )
        self.assertEqual(proposal["state"], "pending_review")
        self.assertFalse(proposal["auto_apply"])

    def test_duplicate_entry_id_rejected(self):
        """Duplicate entry_id should be rejected."""
        ds_lite_experience_ledger.create_ledger("test2", "project-002", self.root)
        ledger_path = str(Path(self.root) / "research" / "artifacts" / "experience-ledger-test2.json")
        entry = ds_lite_experience_ledger.record_experience(
            experience_type="guard",
            title="Check preconditions",
            description="Always check preconditions before execution",
            extensions={"guard_type": "precondition"},
        )
        ds_lite_experience_ledger.append_entry(ledger_path, entry)
        with self.assertRaises(ds_lite_experience_ledger.ExperienceError):
            ds_lite_experience_ledger.append_entry(ledger_path, entry)

    def test_invalid_severity_rejected(self):
        """Invalid severity should be rejected for incident entries."""
        entry = ds_lite_experience_ledger.record_experience(
            experience_type="incident",
            title="Bad severity",
            description="This has an invalid severity",
            extensions={"severity": "invalid"},
        )
        with self.assertRaises(ds_lite_experience_ledger.ExperienceError):
            ds_lite_experience_ledger.validate_experience_entry(entry)


class SkillAdmissionTests(unittest.TestCase):
    def _make_valid_candidate(self):
        return ds_lite_skill_admission.create_skill_candidate(
            skill_id="skill-001",
            name="Test Skill",
            source="https://github.com/example/repo",
            commit_or_version="v1.0.0",
            license="MIT",
            decision="on-demand",
            capabilities=["data-analysis"],
            triggers=["when analyzing data"],
            anti_triggers=["when not analyzing data"],
            dependencies=["pandas"],
            external_effects=["reads from filesystem"],
            permissions=["read"],
            install_mode="explicit",
            tests=["test_skill.py"],
        )

    def test_valid_candidate_passes_gate(self):
        """A valid candidate should pass the admission gate."""
        candidate = self._make_valid_candidate()
        result = ds_lite_skill_admission.check_admission_gate(candidate)
        self.assertEqual(result["verdict"], "pass")

    def test_missing_license_blocks(self):
        """Missing license should block admission."""
        candidate = self._make_valid_candidate()
        candidate["license"] = ""
        result = ds_lite_skill_admission.check_admission_gate(candidate)
        self.assertEqual(result["verdict"], "blocked")
        self.assertIn("source_or_license_unclear", result["rule_ids"])

    def test_missing_triggers_blocks(self):
        """Missing triggers should block admission."""
        candidate = self._make_valid_candidate()
        candidate["triggers"] = []
        result = ds_lite_skill_admission.check_admission_gate(candidate)
        self.assertEqual(result["verdict"], "blocked")

    def test_missing_tests_blocks(self):
        """Missing tests should block admission."""
        candidate = self._make_valid_candidate()
        candidate["tests"] = []
        result = ds_lite_skill_admission.check_admission_gate(candidate)
        self.assertEqual(result["verdict"], "blocked")
        self.assertIn("tests_missing", result["rule_ids"])

    def test_missing_reviewed_at_blocks(self):
        """Missing reviewed_at should block admission."""
        candidate = self._make_valid_candidate()
        candidate["reviewed_at"] = ""
        result = ds_lite_skill_admission.check_admission_gate(candidate)
        self.assertEqual(result["verdict"], "blocked")

    def test_register_skill_success(self):
        """Registering a valid candidate should succeed."""
        candidate = self._make_valid_candidate()
        result = ds_lite_skill_admission.register_skill(candidate)
        self.assertTrue(result["registered"])
        self.assertEqual(result["skill_id"], "skill-001")

    def test_register_skill_failure(self):
        """Registering an invalid candidate should fail."""
        candidate = self._make_valid_candidate()
        candidate["license"] = ""
        result = ds_lite_skill_admission.register_skill(candidate)
        self.assertFalse(result["registered"])
        self.assertEqual(result["reason"], "admission_gate_failed")

    def test_admission_digest_is_stable(self):
        """Admission digest should be stable for the same candidate."""
        candidate1 = self._make_valid_candidate()
        candidate2 = self._make_valid_candidate()
        result1 = ds_lite_skill_admission.check_admission_gate(candidate1)
        result2 = ds_lite_skill_admission.check_admission_gate(candidate2)
        self.assertEqual(result1["admission_digest"], result2["admission_digest"])


if __name__ == "__main__":
    unittest.main()