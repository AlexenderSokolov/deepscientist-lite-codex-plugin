from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins" / "deepscientist-lite"
COMMIT = "91862221b39f7ca16d52ae0e1e9cb6c2bb31a96b"
SKILLS = {
    "nature-academic-search", "nature-citation", "nature-data", "nature-downloader",
    "nature-experiment-log", "nature-figure", "nature-literature-pipeline",
    "nature-paper-to-patent", "nature-paper2ppt", "nature-polishing", "nature-proposal-writer",
    "nature-reader", "nature-ref-verifier", "nature-response", "nature-reviewer",
    "nature-statistics", "nature-writing",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_text_sha256(path: Path) -> str:
    content = path.read_text(encoding="utf-8")
    return hashlib.sha256(content.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")).hexdigest()


class NatureIntegrationTests(unittest.TestCase):
    def test_analysis_write_routes_polishing_without_bypassing_evidence(self) -> None:
        text = (PLUGIN / "skills" / "ds-lite-analysis-write" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("## Writing And Polishing Router", text)
        self.assertIn("nature-polishing", text)
        self.assertIn("do not bypass the typed review gate", text.lower())
        self.assertIn("paper type", text.lower())
        self.assertIn("citation intent", text.lower())

    def test_registry_contains_all_seventeen_skills_and_hidden_shared_layer(self) -> None:
        registry = json.loads((PLUGIN / "references" / "nature-skill-registry.json").read_text(encoding="utf-8"))
        self.assertEqual(registry["upstream"]["commit"], COMMIT)
        self.assertEqual(registry["runtime_skill_count"], 17)
        self.assertEqual({item["skill"] for item in registry["skills"]}, SKILLS)
        self.assertFalse(registry["shared_layer"]["discoverable"])
        discovered = {
            path.name
            for path in (PLUGIN / "skills").iterdir()
            if path.is_dir() and (path / "SKILL.md").is_file()
        }
        self.assertEqual(len(discovered), 26)
        self.assertNotIn("nature-shared", discovered)
        shared = PLUGIN / "skills" / "nature-shared"
        self.assertFalse((shared / "SKILL.md").exists())
        for relative in (
            "manifest.yaml",
            "core/ethics.md",
            "core/paper-type-taxonomy.md",
            "core/reader-workflow.md",
            "core/terminology-ledger.md",
            "journal-formats/nat-comms.md",
        ):
            self.assertTrue((shared / relative).is_file(), relative)

    def test_runtime_entries_preserve_source_body_and_provenance(self) -> None:
        vendor = PLUGIN / "vendor" / "nature-skills" / COMMIT / "skills"
        runtime = PLUGIN / "skills"
        for name in sorted(SKILLS):
            with self.subTest(skill=name):
                source = vendor / name / "SKILL.md"
                entry = runtime / name / "SKILL.md"
                provenance = json.loads((runtime / name / "provenance.json").read_text(encoding="utf-8"))
                source_text = source.read_text(encoding="utf-8")
                entry_text = entry.read_text(encoding="utf-8")
                self.assertIn("# DS Lite Integration Boundary", entry_text)
                self.assertIn("## Preserved Upstream Workflow", entry_text)
                self.assertIn("responsible-exploration-covenant.md", entry_text)
                source_heading = next(line for line in source_text.splitlines() if line.startswith("# "))
                self.assertIn(source_heading, entry_text)
                self.assertEqual(provenance["upstream"]["source_skill_sha256"], canonical_text_sha256(source))
                self.assertTrue((runtime / name / "agents" / "openai.yaml").read_bytes().isascii())

    def test_authorized_vendor_sources_are_present(self) -> None:
        nature_license = PLUGIN / "vendor" / "nature-skills" / COMMIT / "LICENSE"
        autoresearch = PLUGIN / "vendor" / "codex-autoresearch" / "f2389bffbb4cd7789deb6796bc4ba35bf31f2a90"
        self.assertTrue(nature_license.is_file())
        self.assertTrue((autoresearch / "package.json").is_file())
        self.assertTrue((autoresearch / "src").is_dir())
        self.assertTrue((autoresearch / "test").is_dir())


if __name__ == "__main__":
    unittest.main()
