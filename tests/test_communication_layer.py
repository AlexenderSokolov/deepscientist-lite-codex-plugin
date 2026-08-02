from __future__ import annotations

import json
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_ROOT = REPO_ROOT / "plugins" / "deepscientist-lite-core"
COMMUNICATION_ROOT = PLUGIN_ROOT / "references" / "communication"
EXPECTED_SKILLS = {
    "ds-lite",
    "ds-lite-intake",
    "ds-lite-scout",
    "ds-lite-idea",
    "ds-lite-experiment",
    "ds-lite-review",
    "ds-lite-analysis-write",
    "ds-lite-iterate",
    "ds-lite-coordinate",
}
EXPECTED_PROFILES = {
    "research-peer",
    "teaching-explainer",
    "compact-operator",
    "reflective-researcher",
}


class CommunicationLayerTests(unittest.TestCase):
    def test_communication_reference_set_is_fixed_and_progressively_loadable(self) -> None:
        self.assertEqual(
            {path.name for path in COMMUNICATION_ROOT.glob("*.md")},
            {
                "core.md",
                "profiles.md",
                "humanizer-zh.md",
                "humanizer-en.md",
                "academic-writing.md",
                "self-audit.md",
            },
        )
        core = (COMMUNICATION_ROOT / "core.md").read_text(encoding="utf-8")
        self.assertIn("STYLE.md", core)
        self.assertIn("evidence", core.lower())
        self.assertIn("handoff", core.lower())
        for audit_id in ("honor-01", "honor-02", "honor-03", "honor-04", "honor-05", "honor-06", "honor-07", "honor-08"):
            self.assertIn(audit_id, core)
        self.assertIn("Phase 1", (COMMUNICATION_ROOT / "self-audit.md").read_text(encoding="utf-8"))
        self.assertIn("八荣八耻", core)

    def test_profiles_define_four_original_choices_and_reflection_boundary(self) -> None:
        profiles = (COMMUNICATION_ROOT / "profiles.md").read_text(encoding="utf-8")
        for profile in EXPECTED_PROFILES:
            self.assertIn(profile, profiles)
        self.assertIn("不得模仿名人或作者", profiles)
        self.assertIn("reflective-researcher", profiles)
        self.assertIn("可证伪", profiles)

    def test_style_template_exposes_customization_contract(self) -> None:
        style = (PLUGIN_ROOT / "assets" / "templates" / "STYLE.md").read_text(encoding="utf-8")
        for field in ("language", "detail", "academic", "profile", "extends"):
            self.assertIn(field + ":", style)
        self.assertIn("research-peer", style)
        self.assertIn("custom", style)

    def test_all_nine_skills_load_core_style_protection_and_handoff(self) -> None:
        actual = {
            item.name
            for item in (PLUGIN_ROOT / "skills").iterdir()
            if item.is_dir() and (item / "SKILL.md").is_file()
        }
        self.assertEqual(actual, EXPECTED_SKILLS)
        for skill_name in EXPECTED_SKILLS:
            content = (PLUGIN_ROOT / "skills" / skill_name / "SKILL.md").read_text(encoding="utf-8")
            self.assertIn("references/communication/core.md", content)
            self.assertIn("STYLE.md", content)
            self.assertIn("保护", content)
            self.assertIn("Handoff", content)
            self.assertIn("references/communication/self-audit.md", content)
            self.assertIn("Phase 1", content)

    def test_runtime_notice_contains_selected_mit_attributions(self) -> None:
        notice = (PLUGIN_ROOT / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
        for source in (
            "ai-zixun/humanizer-zh@f75f1ac9",
            "blader/humanizer@1b485648",
            "AIScientists-Dev/academic-humanizer@94b88b23",
        ):
            self.assertIn(source, notice)
        self.assertGreaterEqual(notice.count("MIT License"), 3)
        self.assertNotIn("references/communication/upstream", notice)

    def test_style_contract_is_not_a_runtime_state_schema(self) -> None:
        manifest = json.loads((PLUGIN_ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["hooks"], "./hooks/hooks.json")
        self.assertNotIn("mcpServers", manifest)
        self.assertEqual(manifest["version"], "0.8.1-beta.1")


if __name__ == "__main__":
    unittest.main()
