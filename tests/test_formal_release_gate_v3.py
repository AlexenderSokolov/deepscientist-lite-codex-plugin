from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTROLLER_ROOT = ROOT / "plugins" / "deepscientist-lite-core" / "controller"
sys.path.insert(0, str(CONTROLLER_ROOT))

from ds_lite_control.store import ControlStore


class FormalReleaseGateV3Tests(unittest.TestCase):
    def run_gate(
        self,
        root: Path,
        profile: dict[str, object],
        *extra_args: str,
    ) -> subprocess.CompletedProcess[str]:
        control_db = root / "control.sqlite3"
        store = ControlStore(control_db)
        store.close()
        profile_path = root / "profile.json"
        profile_path.write_text(json.dumps(profile), encoding="utf-8")
        return subprocess.run(
            [
                sys.executable,
                str(ROOT / "tools" / "validation" / "formal_release_gate.py"),
                "--schema-version", "ds-lite.formal-release-gate.v3",
                "--control-db", str(control_db),
                "--job-id", "job-1",
                "--release-profile", str(profile_path),
                "--receipt-root", str(root / "receipts"),
                "--output", str(root / "decision.json"),
                *extra_args,
            ],
            text=True,
            encoding="utf-8",
            capture_output=True,
        )

    def test_v3_uses_shared_aggregate_for_fixture_profile(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ds-lite-formal-v3-") as directory:
            root = Path(directory)
            completed = self.run_gate(root, {
                "schema_version": "ds-lite.release-profile.v1",
                "profile_id": "fixture-empty",
                "fixture_only": True,
                "required_gates": [],
            })
            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            decision = json.loads((root / "decision.json").read_text(encoding="utf-8"))
            self.assertEqual(decision["schema_version"], "ds-lite.release-decision.v1")
            self.assertTrue(decision["fixture_only"])
            self.assertTrue(decision["release_allowed"])

    def test_v3_fails_closed_when_gate_decision_is_missing(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ds-lite-formal-v3-") as directory:
            root = Path(directory)
            completed = self.run_gate(root, {
                "schema_version": "ds-lite.release-profile.v1",
                "profile_id": "project-release",
                "fixture_only": False,
                "required_gates": ["gate-a"],
            })
            self.assertEqual(completed.returncode, 2, completed.stdout + completed.stderr)
            decision = json.loads((root / "decision.json").read_text(encoding="utf-8"))
            self.assertEqual(decision["missing_gates"], ["gate-a"])
            self.assertFalse(decision["release_allowed"])

    def test_v3_rejects_legacy_receipts_instead_of_upgrading_them(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ds-lite-formal-v3-") as directory:
            root = Path(directory)
            legacy = root / "legacy.json"
            legacy.write_text(json.dumps({"status": "passed"}), encoding="utf-8")
            completed = self.run_gate(root, {
                "schema_version": "ds-lite.release-profile.v1",
                "profile_id": "project-release",
                "fixture_only": False,
                "required_gates": [],
            }, "--evidence", f"source={legacy}")
            self.assertEqual(completed.returncode, 2)
            self.assertIn("does not accept legacy --evidence", completed.stdout)
            self.assertFalse((root / "decision.json").exists())

    def test_legacy_default_entry_still_emits_v1_shape(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ds-lite-formal-v1-") as directory:
            root = Path(directory)
            output = root / "decision.json"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "tools" / "validation" / "formal_release_gate.py"),
                    "--output", str(output),
                ],
                text=True,
                encoding="utf-8",
                capture_output=True,
            )
            self.assertEqual(completed.returncode, 2)
            decision = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(decision["schema_version"], "ds-lite.formal-release-gate.v1")
            self.assertEqual(decision["profile"], "default")
            self.assertFalse(decision["release_allowed"])


if __name__ == "__main__":
    unittest.main()
