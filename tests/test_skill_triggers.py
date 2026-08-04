from __future__ import annotations

import json
import re
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_ROOT = REPO_ROOT / "plugins" / "deepscientist-lite"
SKILLS_ROOT = PLUGIN_ROOT / "skills"
TRIGGER_MATRIX = PLUGIN_ROOT / "references" / "skill-trigger-matrix.json"
COVENANT = PLUGIN_ROOT / "references" / "responsible-exploration-covenant.md"
REFLECTION_ARCHITECTURE = (
    REPO_ROOT / "docs" / "maintainers" / "action-reflection-philosophy.zh.md"
)
SKILL_NAMES = (
    "ds-lite",
    "ds-lite-intake",
    "ds-lite-scout",
    "ds-lite-idea",
    "ds-lite-experiment",
    "ds-lite-review",
    "ds-lite-analysis-write",
    "ds-lite-iterate",
    "ds-lite-coordinate",
)


def frontmatter_description(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    match = re.match(r"^---\n(.*?)\n---\n", text, flags=re.DOTALL)
    if not match:
        raise AssertionError(f"missing frontmatter: {path}")
    description = re.search(r"^description:\s*(.+)$", match.group(1), flags=re.MULTILINE)
    if not description:
        raise AssertionError(f"missing description: {path}")
    return description.group(1).strip().strip('"')


class SkillTriggerMetadataTests(unittest.TestCase):
    def test_gateway_skill_exists_and_routes_exactly_one_action(self) -> None:
        path = SKILLS_ROOT / "ds-lite" / "SKILL.md"
        self.assertTrue(path.is_file(), "missing ninth $ds-lite gateway")
        text = path.read_text(encoding="utf-8")
        self.assertIn("exactly one", text)
        self.assertIn("Mission Board", text)
        self.assertIn("why", text.lower())
        self.assertNotIn("while true", text.lower())
        self.assertNotIn("run indefinitely", text.lower())

    def test_descriptions_use_user_scenarios_instead_of_codex_should(self) -> None:
        for name in SKILL_NAMES:
            with self.subTest(skill=name):
                description = frontmatter_description(SKILLS_ROOT / name / "SKILL.md")
                self.assertTrue(description.startswith("Use when"))
                self.assertFalse(description.startswith("Use when Codex should"))
                self.assertGreaterEqual(len(description), 80)

    def test_all_skill_metadata_allows_implicit_invocation(self) -> None:
        for name in SKILL_NAMES:
            with self.subTest(skill=name):
                metadata = (SKILLS_ROOT / name / "agents" / "openai.yaml").read_text(encoding="utf-8")
                self.assertIn("policy:", metadata)
                self.assertIn("allow_implicit_invocation: true", metadata)

    def test_manifest_uses_three_high_value_entry_prompts(self) -> None:
        manifest = json.loads((PLUGIN_ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
        prompts = manifest["interface"]["defaultPrompt"]
        self.assertEqual(len(prompts), 3)
        self.assertTrue(prompts[0].startswith("$ds-lite "))
        self.assertIn("Twenty-six skills", manifest["interface"]["longDescription"])

    def test_trigger_matrix_separates_relevant_and_near_miss_prompts(self) -> None:
        payload = json.loads(TRIGGER_MATRIX.read_text(encoding="utf-8"))
        self.assertEqual(payload["schema_version"], "ds-lite.skill-trigger-matrix.v1")
        relevant = payload["relevant"]
        near_miss = payload["near_miss"]
        self.assertGreaterEqual(len(relevant), 10)
        self.assertGreaterEqual(len(near_miss), 4)
        self.assertEqual({item["expected_skill"] for item in relevant}, set(SKILL_NAMES))
        self.assertTrue(all(item["expected_skill"] == "none" for item in near_miss))
        self.assertTrue(all(item["prompt"].strip() for item in relevant + near_miss))
        self.assertEqual(payload["validation_status"], "static-only / forward-test-not-verified")

    def test_all_skills_share_one_responsible_exploration_and_feedback_protocol(self) -> None:
        self.assertTrue(COVENANT.is_file(), "missing responsible exploration covenant")
        for name in SKILL_NAMES:
            with self.subTest(skill=name):
                text = (SKILLS_ROOT / name / "SKILL.md").read_text(encoding="utf-8")
                self.assertIn("responsible-exploration-covenant.md", text)
                self.assertIn("start / progress / end", text)
                self.assertIn("mandatory Start report", text)
                self.assertIn("mandatory End report", text)

    def test_covenant_encodes_seven_checkable_actions_and_redacted_feedback(self) -> None:
        self.assertTrue(COVENANT.is_file(), "missing responsible exploration covenant")
        text = COVENANT.read_text(encoding="utf-8")
        required = (
            "Situation before hypothesis",
            "Facts, hypotheses, values, and authorization",
            "One bounded reversible action",
            "Prediction, falsification, budget, and stop condition",
            "Preserve negative results",
            "Irreversible actions return to the user",
            "Reflect and report after action",
            "at least every 60 seconds",
            "hidden reasoning",
            "absolute workstation root",
        )
        for anchor in required:
            with self.subTest(anchor=anchor):
                self.assertIn(anchor, text)
        self.assertEqual(text.count("### "), 7)

    def test_feedback_contract_is_mandatory_and_cross_platform(self) -> None:
        text = COVENANT.read_text(encoding="utf-8")
        required = (
            "MANDATORY",
            "Goal",
            "Observed facts",
            "Authorization boundary",
            "Checkpoint",
            "What changed",
            "Verification evidence",
            "Failure layer",
            "Unverified items",
            "Next action",
            "User decision required",
            "Windows",
            "Linux",
            "PowerShell",
            "Bash",
            "rate-limit",
            "timeout",
            "provider-unavailable",
        )
        for anchor in required:
            with self.subTest(anchor=anchor):
                self.assertIn(anchor, text)

        gateway = (SKILLS_ROOT / "ds-lite" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("Do not start the action until", gateway)
        self.assertIn("mandatory Start report", gateway)
        self.assertIn("Do not finish with a bare success sentence", gateway)

    def test_gateway_wires_handoff_cli_boundaries_and_selective_superpowers(self) -> None:
        gateway = (SKILLS_ROOT / "ds-lite" / "SKILL.md").read_text(encoding="utf-8")
        coordinate = (SKILLS_ROOT / "ds-lite-coordinate" / "SKILL.md").read_text(encoding="utf-8")
        covenant = COVENANT.read_text(encoding="utf-8")
        for text in (gateway, coordinate, covenant):
            self.assertIn("ds-lite.handoff.v1", text)
            self.assertIn("CLI boundary", text)
        adaptation = (PLUGIN_ROOT / "references" / "selective-superpowers-adaptation.md").read_text(encoding="utf-8")
        self.assertIn("check applicable skills", adaptation)
        self.assertIn("automatic retries", adaptation)

    def test_iterate_uses_running_receipt_before_action_and_terminal_reflection_after(self) -> None:
        text = (SKILLS_ROOT / "ds-lite-iterate" / "SKILL.md").read_text(encoding="utf-8")
        ordered = (
            "ds_lite_iteration.py init",
            "plan -> act -> verify -> reflect -> report -> stop",
            "completed|partial|blocked|failed|ambiguous",
            "ds_lite_iteration.py finalize",
            "ds_lite_iteration.py verify",
            "render-status",
        )
        positions = []
        for anchor in ordered:
            with self.subTest(anchor=anchor):
                self.assertIn(anchor, text)
                positions.append(text.index(anchor))
        self.assertEqual(positions, sorted(positions))
        self.assertIn("not an exactly-once transaction", text)
        self.assertIn("Do not start a reflection loop", text)

    def test_reflective_architecture_is_wired_into_docs_and_validation(self) -> None:
        if not REFLECTION_ARCHITECTURE.is_file():
            self.skipTest("maintainer docs are private (gitignored)")
        architecture = REFLECTION_ARCHITECTURE.read_text(encoding="utf-8")
        for anchor in (
            "行动哲学",
            "存在主义",
            "负责任探索",
            "ds-lite.iteration.v1",
            "latest_iteration",
            "hypothesis_pool",
            "fresh-host",
            "not-verified",
        ):
            with self.subTest(anchor=anchor):
                self.assertIn(anchor, architecture)

        project_path = REPO_ROOT / "PROJECT.md"
        if not project_path.is_file():
            self.skipTest("PROJECT.md is private (gitignored)")
        project = project_path.read_text(encoding="utf-8")
        for anchor in (
            "九个 `ds-lite-*` skills",
            "ds-lite.iteration.v1",
            "latest_iteration",
            "hypothesis_pool",
            "Hook fresh-host",
        ):
            with self.subTest(project_anchor=anchor):
                self.assertIn(anchor, project)

        implementation = (REPO_ROOT / "docs" / "implementation.zh.md").read_text(
            encoding="utf-8"
        )
        user_guide = (REPO_ROOT / "docs" / "user-guide.zh.md").read_text(encoding="utf-8")
        self.assertIn("最小 reflective iteration", implementation)
        self.assertIn("不是 exactly-once transaction", implementation)
        self.assertIn("行动、验证、反思、汇报", user_guide)

        validator = (REPO_ROOT / "tools" / "validation" / "validate_repo.py").read_text(
            encoding="utf-8"
        )
        for anchor in (
            "action-reflection-philosophy.zh.md",
            "responsible-exploration-covenant.md",
            "ds_lite_iteration.py",
            "ds_lite_hook.py",
            "action-reflection-student.zh.md",
        ):
            with self.subTest(validator_anchor=anchor):
                self.assertIn(anchor, validator)

        compile_targets = (
            "plugins/deepscientist-lite/scripts/ds_lite_hook.py",
            "plugins/deepscientist-lite/scripts/ds_lite_iteration.py",
            "tests/test_hooks.py",
            "tests/test_iteration.py",
            "tests/test_skill_triggers.py",
        )
        for runner in (
            REPO_ROOT / "tools" / "validation" / "run_validate.ps1",
            REPO_ROOT / "tools" / "validation" / "run_validate.sh",
        ):
            runner_text = runner.read_text(encoding="utf-8")
            for target in compile_targets:
                with self.subTest(runner=runner.name, target=target):
                    self.assertIn(target, runner_text)


if __name__ == "__main__":
    unittest.main()
