from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from teaching.offline_loop_acceptance import run


class OfflineLoopAcceptanceTests(unittest.TestCase):
    def test_fake_loop_passes_and_external_adapter_is_frozen(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ds-lite-offline-loop-") as directory:
            report = run(Path(directory) / "receipt")
            self.assertEqual(report["status"], "passed")
            self.assertEqual(report["offline_loop_status"], "passed")
            self.assertEqual(report["external_adapter_status"], "blocked-not-verified")
            self.assertFalse(report["external_process_spawn_observed"])
            persisted = json.loads((Path(directory) / "receipt" / "offline-loop-acceptance.json").read_text(encoding="utf-8"))
            self.assertFalse(persisted["real_gates_unlocked"])

    def test_existing_output_is_refused(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ds-lite-offline-loop-") as directory:
            output = Path(directory) / "receipt"
            output.mkdir()
            with self.assertRaises(RuntimeError):
                run(output)


if __name__ == "__main__":
    unittest.main()
