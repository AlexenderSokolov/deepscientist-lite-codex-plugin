import tempfile
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
CONTROLLER_ROOT = ROOT / "plugins" / "deepscientist-lite-core" / "controller"
sys.path.insert(0, str(CONTROLLER_ROOT))

from phase2_fault_harness import run_matrix


class Phase2FaultHarnessTests(unittest.TestCase):
    def test_fixed_seed_matrix_covers_k4_to_k7_and_k12(self):
        with tempfile.TemporaryDirectory(prefix="ds-lite-phase2-fault-") as directory:
            root = Path(directory)
            result = run_matrix(root / "work", root / "receipt", seed=20260731, trials=2)
            self.assertEqual(set(result["cases"]), {"K4", "K5", "K6", "K7", "K12"})
            self.assertTrue(all(case["all_passed"] for case in result["cases"].values()))
            self.assertTrue(result["external_process_termination"])
            self.assertEqual(result["evidence_class"], "fake-host-external-process")
            self.assertFalse(result["release_allowed"])


if __name__ == "__main__":
    unittest.main()
