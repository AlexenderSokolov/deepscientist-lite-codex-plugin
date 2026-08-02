from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from teaching import trusted_hook_fixture


class TrustedHookFixtureTests(unittest.TestCase):
    def test_terminal_fixture_closes_iteration_and_creates_learning_receipt(self) -> None:
        with tempfile.TemporaryDirectory(dir=os.environ.get("TEMP")) as directory:
            root = Path(directory) / "workspace"
            root.mkdir()
            receipt = trusted_hook_fixture.prepare(root, terminal=True)
            self.assertTrue(receipt["terminal_fixture_prepared"])
            self.assertEqual(receipt["agent_initiated_terminal_closure"], "not-observed")
            iteration = json.loads((root / receipt["iteration_ref"]).read_text(encoding="utf-8"))
            self.assertEqual(iteration["status"], "completed")
            self.assertTrue(iteration["extensions"]["fixture_prepared"])
            self.assertTrue((root / "research" / "learning" / "ds-lite-iterate.json").is_file())

    def test_fixture_refuses_existing_workspace_state(self) -> None:
        with tempfile.TemporaryDirectory(dir=os.environ.get("TEMP")) as directory:
            root = Path(directory)
            (root / "PROJECT.md").write_text("existing", encoding="utf-8")
            with self.assertRaises(trusted_hook_fixture.FixtureError):
                trusted_hook_fixture.prepare(root, terminal=True)


if __name__ == "__main__":
    unittest.main()
