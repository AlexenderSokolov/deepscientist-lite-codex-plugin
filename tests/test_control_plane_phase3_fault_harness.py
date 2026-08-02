from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTROLLER_ROOT = ROOT / "plugins" / "deepscientist-lite-core" / "controller"
DBOS_ROOT = ROOT / "research" / ".validation-tmp" / "phase0.5-dbos-20260731"
sys.path.insert(0, str(CONTROLLER_ROOT))

from phase3_fault_harness import run_matrix


class Phase3FaultHarnessTests(unittest.TestCase):
    def test_fixed_seed_matrix_covers_k10_and_k11_with_external_processes(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ds-lite-phase3-fault-") as directory:
            root = Path(directory)
            result = run_matrix(
                root / "work", root / "fault-matrix.json",
                python_bin=Path(sys.executable), dependency_root=DBOS_ROOT,
                seed=20260731, trials=2, timeout=20,
            )
            self.assertEqual(set(result["cases"]), {"K10", "K11"})
            self.assertTrue(all(case["all_passed"] for case in result["cases"].values()))
            self.assertTrue(result["external_process_termination"])
            self.assertEqual(result["cases"]["K11"]["evidence_class"], "real-dbos-sqlite-external-process")
            self.assertFalse(result["release_allowed"])


if __name__ == "__main__":
    unittest.main()
