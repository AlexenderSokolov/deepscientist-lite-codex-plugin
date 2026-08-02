from __future__ import annotations

import sys
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTROLLER_ROOT = ROOT / "plugins" / "deepscientist-lite-core" / "controller"
sys.path.insert(0, str(CONTROLLER_ROOT))

from teaching.control_plane_phase4_fault_harness import CASES, run_matrix


class Phase4FaultHarnessTests(unittest.TestCase):
    def test_harness_cli_bootstraps_the_repository_controller_package(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(ROOT / "teaching" / "control_plane_phase4_fault_harness.py"), "--help"],
            capture_output=True, text=True, timeout=15,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("--trials", completed.stdout)

    def test_fixed_seed_matrix_recovers_all_four_write_once_cut_points(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ds-lite-phase4-fault-") as directory:
            root = Path(directory)
            result = run_matrix(
                root / "work",
                root / "phase4-fault-matrix.json",
                python_bin=Path(sys.executable),
                seed=20260801,
                trials=2,
                timeout=15,
            )

            self.assertEqual(set(result["cases"]), set(CASES))
            self.assertEqual(result["status"], "passed")
            self.assertTrue(result["external_process_termination"])
            self.assertFalse(result["release_allowed"])
            for case in result["cases"].values():
                self.assertTrue(case["all_passed"])
                self.assertEqual(case["passed"], 2)
                self.assertTrue(case["receipt_file_preserved"])
                self.assertTrue(case["index_reconciled"])
                self.assertTrue(case["idempotent_replay"])
                self.assertTrue(case["stale_fence_rejected"])

    def test_matrix_refuses_to_reuse_work_or_output_paths(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ds-lite-phase4-fault-path-") as directory:
            root = Path(directory)
            work = root / "work"
            work.mkdir()
            with self.assertRaises(FileExistsError):
                run_matrix(
                    work,
                    root / "phase4-fault-matrix.json",
                    python_bin=Path(sys.executable),
                    seed=1,
                    trials=1,
                )


if __name__ == "__main__":
    unittest.main()
