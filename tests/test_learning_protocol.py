from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "plugins" / "deepscientist-lite-core" / "scripts" / "ds_lite_learning.py"


class LearningProtocolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="ds-lite-learning-"))
        (self.root / "PROJECT.md").write_text("# project\n", encoding="utf-8")

    def run_cli(self, *args: str, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args], cwd=REPO_ROOT,
            input=input_text, text=True, encoding="utf-8", capture_output=True,
        )

    def test_learn_writes_receipt_and_summary_with_catalog_hashes(self) -> None:
        result = self.run_cli(
            "learn", "--root", str(self.root), "--skill", "ds-lite",
            "--summary", "Applicability: recover one bounded project step. Rules: read the Mission Board and preserve evidence. Pitfalls: treating an artifact as completion. Checklist: verify state, evidence, and rollback. Human: approve the next step.",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["schema_version"], "ds-lite.learning-receipt.v1")
        receipt = self.root / payload["receipt_ref"]
        summary = self.root / payload["summary_ref"]
        self.assertTrue(receipt.is_file())
        self.assertTrue(summary.is_file())
        data = json.loads(receipt.read_text(encoding="utf-8"))
        self.assertEqual(data["status"], "current")
        self.assertEqual(data["skill"], "ds-lite")
        self.assertTrue(data["tutorial_refs"])

    def test_matching_learning_is_reused_and_version_change_is_stale(self) -> None:
        first = self.run_cli("learn", "--root", str(self.root), "--skill", "ds-lite", "--summary", "Applicability: recovery. Rules: read state. Pitfalls: claiming completion. Checklist: verify receipt. Human: approve next step.")
        self.assertEqual(first.returncode, 0, first.stderr)
        second = self.run_cli("ensure", "--root", str(self.root), "--skill", "ds-lite")
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(json.loads(second.stdout)["status"], "current")
        receipt = self.root / json.loads(first.stdout)["receipt_ref"]
        data = json.loads(receipt.read_text(encoding="utf-8"))
        data["package_version"] = "0.7.0-beta.1"
        receipt.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        stale = self.run_cli("ensure", "--root", str(self.root), "--skill", "ds-lite")
        self.assertNotEqual(stale.returncode, 0)
        self.assertIn("stale", stale.stdout.lower() + stale.stderr.lower())

    def test_tutorial_catalog_is_bounded_and_hash_verified(self) -> None:
        result = self.run_cli("catalog")
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertLessEqual(len(data["tutorials"]), 10)
        for item in data["tutorials"]:
            self.assertLessEqual(len((REPO_ROOT / "plugins" / "deepscientist-lite-core" / item["path"]).read_text(encoding="utf-8")), 4000)
            self.assertEqual(len(item["sha256"]), 64)


if __name__ == "__main__":
    unittest.main()
