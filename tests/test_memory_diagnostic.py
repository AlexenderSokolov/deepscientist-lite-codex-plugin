from __future__ import annotations

import json
import os
import tempfile
import unittest
import uuid
from pathlib import Path

from teaching.memory_diagnostic import run


class MemoryDiagnosticTests(unittest.TestCase):
    def test_diagnostic_writes_redacted_bounded_receipt(self) -> None:
        root = Path(__file__).resolve().parents[1]
        parent = Path(os.environ.get("TEMP_ROOT", os.environ.get("DS_LITE_TEST_ROOT", root / ".tmp-test-artifacts")))
        parent.mkdir(parents=True, exist_ok=True)
        temp = parent / f"ds-lite-memory-{uuid.uuid4().hex[:12]}"
        temp.mkdir(parents=True, exist_ok=False)
        output = temp / "memory.json"
        receipt = run(root, output, iterations=3, max_growth_bytes=1024 * 1024)
        self.assertEqual(receipt["status"], "passed")
        self.assertFalse(receipt["raw_input_persisted"])
        self.assertNotIn("prompt", json.dumps(receipt).lower())
        self.assertEqual(receipt["sample_count"], 3)
        self.assertTrue(all(set(sample) == {
            "current_bytes", "peak_bytes", "current_delta_bytes", "process_peak_bytes"
        } for sample in receipt["samples"]))
        self.assertGreaterEqual(receipt["process_peak_bytes_final"], 0)
        self.assertEqual(
            json.loads(output.read_text(encoding="utf-8"))["schema_version"],
            "ds-lite.memory-diagnostic.v1",
        )


if __name__ == "__main__":
    unittest.main()
