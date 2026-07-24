from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from teaching import nature_runtime_acceptance


ROOT = Path(__file__).resolve().parents[1]


class NatureRuntimeAcceptanceTests(unittest.TestCase):
    def test_wrappers_are_ascii_and_delegate_through_argv(self) -> None:
        for name in ("run_nature_runtime_acceptance.ps1", "run_nature_runtime_acceptance.sh"):
            path = ROOT / "teaching" / name
            source = path.read_text(encoding="ascii")
            self.assertIn("nature_runtime_acceptance.py", source)
            self.assertNotIn("python -c", source.lower())
            self.assertNotIn("SECRET_MARKER", source)

    def test_build_report_covers_all_skills_without_unlocking_real_gates(self) -> None:
        report = nature_runtime_acceptance.build_report(ROOT)
        self.assertEqual(report["schema_version"], "ds-lite.nature-runtime-acceptance.v1")
        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["skill_count"], 17)
        self.assertFalse(report["shared_layer_discoverable"])
        self.assertFalse(report["real_gates_unlocked"])
        self.assertEqual(len(report["skills"]), 17)
        self.assertTrue(all(item["route_status"] == "passed" for item in report["skills"]))
        self.assertTrue(all("runtime_probe_status" in item for item in report["skills"]))
        self.assertTrue(all("warning_count" in item["runtime_probe"] for item in report["skills"]))

    def test_write_report_is_fresh_only_and_redacted(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            output = Path(raw) / "nature-runtime.json"
            report = nature_runtime_acceptance.write_report(ROOT, output)
            persisted = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(persisted, report)
            serialized = output.read_text(encoding="utf-8")
            self.assertNotIn(str(ROOT), serialized)
            self.assertNotIn("SECRET_MARKER", serialized)
            with self.assertRaises(nature_runtime_acceptance.AcceptanceError):
                nature_runtime_acceptance.write_report(ROOT, output)


if __name__ == "__main__":
    unittest.main()
