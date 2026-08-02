from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.validation import audit_superpowers


class SuperpowersCompatibilityTests(unittest.TestCase):
    def test_absent_install_keeps_ds_lite_ownership(self) -> None:
        result, returncode = audit_superpowers.audit(None, None)
        self.assertEqual(returncode, 0)
        self.assertEqual(result["state"], "absent")
        self.assertEqual(result["delegated_process_roles"], [])

    def test_present_install_delegates_only_process_roles(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in audit_superpowers.EXPECTED_SKILLS:
                skill = root / name / "SKILL.md"
                skill.parent.mkdir(parents=True)
                skill.write_text(f"# {name}\n", encoding="utf-8")
            result, returncode = audit_superpowers.audit(str(root), None)
        self.assertEqual(returncode, 0)
        self.assertEqual(result["state"], "present")
        self.assertIn("verification", result["delegated_process_roles"])
        self.assertIn("approval", result["ds_lite_ownership"])

    def test_conflicting_ownership_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            policy = Path(directory) / "policy.json"
            policy.write_text(json.dumps({"owners": {"stop_gate": "superpowers"}}), encoding="utf-8")
            result, returncode = audit_superpowers.audit(None, str(policy))
        self.assertEqual(returncode, 2)
        self.assertEqual(result["state"], "conflict")
        self.assertEqual(result["status"], "blocked")


if __name__ == "__main__":
    unittest.main()
