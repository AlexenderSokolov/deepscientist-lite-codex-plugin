import json
import tempfile
import unittest
from pathlib import Path

from tools.validation.phase5_legacy_compatibility import build

DIGEST = "a" * 64


def write(path: Path, value: dict) -> Path:
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


class Phase5LegacyCompatibilityTests(unittest.TestCase):
    def candidate(self, root: Path) -> Path:
        return write(root / "candidate.json", {
            "schema_version": "ds-lite.phase5-release-candidate.v1",
            "candidate_digest": DIGEST,
        })

    def test_cli_requires_all_three_current_candidate_sources(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inputs = []
            for name, schema in (
                ("runtime", "ds-lite.runtime-compatibility.v1"),
                ("action", "ds-lite.phase5-real-codex-action-v2.v1"),
                ("cache", "ds-lite.formal-cache-acceptance.v1"),
            ):
                inputs.append((name, write(root / f"{name}.json", {
                    "schema_version": schema, "status": "passed", "candidate_digest": DIGEST,
                })))
            receipt = build("cli", self.candidate(root), inputs, root / "out.json")
            self.assertEqual(receipt["schema_version"], "ds-lite.cli-acceptance.v1")
            self.assertTrue(receipt["candidate_bound"])
            with self.assertRaisesRegex(ValueError, "incomplete"):
                build("cli", self.candidate(root), inputs[:-1], root / "bad.json")

    def test_historical_surface_requires_current_candidate_support(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            historical = write(root / "delegation.json", {
                "schema_version": "ds-lite.real-delegation-acceptance.v1", "status": "passed",
            })
            current = write(root / "desktop.json", {
                "schema_version": "ds-lite.fresh-desktop-acceptance.v1", "status": "passed",
                "candidate_digest": DIGEST,
            })
            receipt = build("delegation", self.candidate(root), [
                ("historical", historical), ("current", current),
            ], root / "out.json")
            self.assertEqual(receipt["status"], "passed")
            with self.assertRaisesRegex(ValueError, "incomplete"):
                build("delegation", self.candidate(root), [("historical", historical)], root / "bad.json")

    def test_hook_repair_requires_deterministic_same_turn_checks(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            hook = write(root / "hook.json", {
                "schema_version": "ds-lite.trusted-hook-acceptance.v1", "status": "passed",
                "candidate_digest": DIGEST,
                "checks": {"same_turn_stop_repair": True, "single_turn": True, "real_host_terminal": True},
            })
            receipt = build("hook_in_turn_repair", self.candidate(root), [("hook", hook)], root / "out.json")
            self.assertTrue(receipt["deterministic_verifier"])
            self.assertTrue(receipt["release_evidence"])
            self.assertTrue(receipt["verified_turn_id"].startswith("redacted:"))


if __name__ == "__main__":
    unittest.main()
