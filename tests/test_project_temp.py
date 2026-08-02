from __future__ import annotations

import os
import unittest
from pathlib import Path
from unittest import mock

from tools.validation.project_temp import default_temp_root, project_temp_dir


class ProjectTempTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(__file__).resolve().parents[1]
        self.fixed = (self.root / "research" / ".validation-tmp").resolve()

    def test_default_is_project_volume(self) -> None:
        with mock.patch.dict(os.environ, {"TEMP_ROOT": ""}, clear=False):
            self.assertEqual(default_temp_root(self.root), self.fixed)

    def test_external_system_temp_root_is_rejected(self) -> None:
        with mock.patch.dict(os.environ, {"TEMP_ROOT": r"C:\Windows\Temp\ds-lite"}, clear=False):
            with self.assertRaises(ValueError):
                default_temp_root(self.root)

    def test_child_temp_root_is_allowed(self) -> None:
        child = self.fixed / "test-project-temp"
        with mock.patch.dict(os.environ, {"TEMP_ROOT": str(child)}, clear=False):
            created = project_temp_dir(self.root, prefix="policy-")
        self.assertEqual(created.parent, child)
        self.assertTrue(created.is_dir())


if __name__ == "__main__":
    unittest.main()
