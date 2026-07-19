from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
COMMUNICATION = REPO_ROOT / "plugins" / "deepscientist-lite" / "references" / "communication"
MANIFEST = COMMUNICATION / "upstream" / "_manifests" / "source-files.json"
MATRIX = COMMUNICATION / "upstream-adoption.json"
AUDIT_TOOL = REPO_ROOT / "tools" / "validation" / "audit_upstream_adoption.py"
ENTRY_FIELDS = {
    "repository", "commit", "source_path", "source_sha256", "decision",
    "local_refs", "rule_ids", "reason", "test_refs",
}


class UpstreamAdoptionTests(unittest.TestCase):
    def test_matrix_contains_each_manifest_file_once_with_exact_public_fields(self) -> None:
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        matrix = json.loads(MATRIX.read_text(encoding="utf-8"))
        self.assertEqual(len(manifest["entries"]), 39)
        self.assertEqual(len(matrix["entries"]), 39)
        expected = {(item["repository"], item["commit"], item["source_path"]) for item in manifest["entries"]}
        actual = {(item["repository"], item["commit"], item["source_path"]) for item in matrix["entries"]}
        self.assertEqual(actual, expected)
        self.assertEqual(len(actual), len(matrix["entries"]))
        for item in matrix["entries"]:
            self.assertEqual(set(item), ENTRY_FIELDS)
            self.assertTrue(item["local_refs"])
            self.assertTrue(item["rule_ids"])
            self.assertTrue(item["reason"])
            self.assertTrue(item["test_refs"])

    def test_snapshot_hashes_and_three_licenses_match_manifest(self) -> None:
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        licenses = 0
        for item in manifest["entries"]:
            snapshot = REPO_ROOT / str(item["local_snapshot"]).replace("\\", "/")
            self.assertTrue(snapshot.is_file(), item["local_snapshot"])
            self.assertEqual(hashlib.sha256(snapshot.read_bytes()).hexdigest(), item["source_sha256"])
            if item["source_path"] == "LICENSE":
                licenses += 1
        self.assertEqual(licenses, 3)

    def test_runtime_skills_never_load_upstream_snapshot(self) -> None:
        for skill in (REPO_ROOT / "plugins" / "deepscientist-lite" / "skills").glob("*/SKILL.md"):
            self.assertNotIn("references/communication/upstream/", skill.read_text(encoding="utf-8"))

    def test_deterministic_audit_tool_passes(self) -> None:
        result = subprocess.run(
            [sys.executable, str(AUDIT_TOOL)], cwd=REPO_ROOT,
            text=True, encoding="utf-8", capture_output=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
