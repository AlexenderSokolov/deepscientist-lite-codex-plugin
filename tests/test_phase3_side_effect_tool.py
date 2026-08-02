from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from teaching.phase3_side_effect_tool import record_side_effect
from teaching.controller_phase3_multigate_worker import side_effect_command


class Phase3SideEffectToolTests(unittest.TestCase):
    def test_prompt_command_uses_absolute_side_effect_root(self) -> None:
        command = side_effect_command(Path("relative-side-effect"))
        self.assertIn(str(Path("relative-side-effect").resolve()), command)
        self.assertIn(str(Path(__file__).resolve().parents[1] / "teaching" / "phase3_side_effect_tool.py"), command)

    def test_duplicate_is_journaled_without_overwriting_marker(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            record_side_effect(root)
            marker = root / "side-effect-marker.txt"
            original = marker.read_bytes()

            with self.assertRaises(FileExistsError):
                record_side_effect(root)

            self.assertEqual(marker.read_bytes(), original)
            journal = root / "side-effect-invocations.jsonl"
            self.assertEqual(len(journal.read_text(encoding="utf-8").splitlines()), 2)


if __name__ == "__main__":
    unittest.main()
