from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "plugins" / "deepscientist-lite-academic" / "scripts" / "ds_lite_academic_state.py"
SPEC = importlib.util.spec_from_file_location("academic_state", SCRIPT)
assert SPEC and SPEC.loader
academic_state = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(academic_state)


class AcademicContractTests(unittest.TestCase):
    def test_registry_declares_all_profiles_and_clean_descriptions(self) -> None:
        registry = academic_state.load_registry()
        self.assertEqual(len(registry["skills"]), 17)
        for item in registry["skills"]:
            self.assertEqual(item["workflow_profile"], "academic-evidence-v1")
            skill = ROOT / "plugins" / "deepscientist-lite-academic" / "skills" / item["skill"] / "SKILL.md"
            description = next(line.split(":", 1)[1].strip() for line in skill.read_text(encoding="utf-8").splitlines() if line.startswith("description:"))
            self.assertLessEqual(len(description), 700)
            self.assertIn(description[-1], ".!?。！？")
            self.assertNotRegex(description.lower(), r"license|tags?|related_skills|related skills")

    def test_preflight_requires_project_work_unit_and_authorization(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "PROJECT.md").write_text("# project\n", encoding="utf-8")
            (root / "research").mkdir()
            (root / "research" / "work-unit.json").write_text("{}", encoding="utf-8")
            (root / "approvals").mkdir()
            (root / "approvals" / "user.md").write_text("approved\n", encoding="utf-8")
            result = academic_state.preflight(
                root, "nature-reader", "research/work-unit.json", 3, "approvals/user.md", "research/artifacts/reader"
            )
            self.assertEqual(result["status"], "ready")
            self.assertTrue(result["review_required"])
            self.assertFalse(result["external_write_allowed"])


if __name__ == "__main__":
    unittest.main()
