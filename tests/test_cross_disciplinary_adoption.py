from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

from tools.validation import audit_upstream_adoption


ROOT = Path(__file__).resolve().parents[1]


class CrossDisciplinaryAdoptionTests(unittest.TestCase):
    def test_upstream_snapshot_audit_accepts_windows_text_checkout(self) -> None:
        self.assertEqual(audit_upstream_adoption.validate(), [])

    def test_active_registry_pins_audited_upstreams_and_clean_room_decisions(self) -> None:
        registry = json.loads(
            (ROOT / "evaluation" / "cross-disciplinary-upstreams.json").read_text(encoding="utf-8")
        )
        self.assertEqual(registry["schema_version"], "ds-lite.upstream-adoption.v1")
        self.assertEqual(registry["observed_on"], "2026-07-27")
        entries = registry["upstreams"]
        expected_ids = {
            "opencli",
            "ars-codex",
            "claude-scholar",
            "ai-research-skills",
            "auto-empirical",
            "scientific-agent-skills",
            "codex-claude-academic-skills",
            "aris",
            "kim-service",
        }
        self.assertEqual({entry["id"] for entry in entries}, expected_ids)
        for entry in entries:
            with self.subTest(upstream=entry["id"]):
                self.assertRegex(entry["commit"], r"^[0-9a-f]{40}$")
                self.assertIn(entry["classification"], {"core", "profile", "fixture", "reject"})
                self.assertIn(
                    entry["decision"],
                    {"clean-room", "companion", "fixture-only", "deferred", "reject", "challenger"},
                )
                self.assertFalse(entry["copied_content"])
                self.assertGreaterEqual(len(entry["audited_files"]), 2)
                for audited in entry["audited_files"]:
                    self.assertRegex(audited["sha256"], r"^[0-9a-f]{64}$")

    def test_opencli_entry_is_pinned_as_a_public_only_challenger(self) -> None:
        registry = json.loads(
            (ROOT / "evaluation" / "cross-disciplinary-upstreams.json").read_text(encoding="utf-8")
        )
        entry = next(item for item in registry["upstreams"] if item["id"] == "opencli")
        self.assertEqual(entry["version"], "1.8.6")
        self.assertEqual(entry["license"], "Apache-2.0")
        self.assertEqual(entry["classification"], "fixture")
        self.assertEqual(entry["decision"], "challenger")
        self.assertRegex(entry["package_integrity"], r"^sha512-[A-Za-z0-9+/]+={0,2}$")
        self.assertRegex(entry["tarball_sha256"], r"^[0-9a-f]{64}$")
        self.assertIn("daemon", entry["not_adopted"])
        self.assertIn("logged-in-browser", entry["not_adopted"])

    def test_new_domain_packs_do_not_vendor_upstream_repositories(self) -> None:
        for name in ("deepscientist-lite-empirical", "deepscientist-lite-engineering"):
            with self.subTest(pack=name):
                self.assertFalse((ROOT / "plugins" / name / "vendor").exists())


if __name__ == "__main__":
    unittest.main()
