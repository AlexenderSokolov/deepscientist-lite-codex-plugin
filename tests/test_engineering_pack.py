from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / "plugins" / "deepscientist-lite-engineering"
SCRIPT = PACK / "scripts" / "ds_lite_engineering.py"


def load_module():
    spec = importlib.util.spec_from_file_location("ds_lite_engineering", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


engineering = load_module()


class EngineeringPackTests(unittest.TestCase):
    def analysis(self):
        return {
            "schema_version": "ds-lite.engineering-analysis.v1",
            "analysis_id": "fft-1",
            "task": "Resolve 50 Hz and 120 Hz components",
            "backend": {"name": "python", "status": "available", "version": "3.12"},
            "units": {"time": "s", "signal": "V", "frequency": "Hz"},
            "sampling": {"rate_hz": 1000.0, "sample_count": 2000, "duration_s": 2.0},
            "preprocessing": ["remove-mean"],
            "fft": {"window": "hann", "resolution_hz": 0.5, "scaling": "single-sided-amplitude"},
            "simulation": {"used": True, "random_seed": 42},
            "checks": {
                "units": "passed", "dimensions": "passed", "aliasing": "passed",
                "leakage": "passed", "figure_axes": "passed",
            },
            "commands": ["python analysis/fft.py"],
            "artifact_refs": ["research/results/fft-1.json", "research/figures/fft-1.png"],
            "evidence_pack_ref": "research/evidence/fft-1/evidence-pack.json",
            "extensions": {},
        }

    def test_valid_fft_contract_computes_consistent_resolution(self) -> None:
        validated = engineering.validate_analysis(self.analysis())
        self.assertEqual(validated["fft"]["resolution_hz"], 0.5)

    def test_bad_sample_rate_unit_conflict_and_wrong_resolution_block(self) -> None:
        bad_rate = self.analysis()
        bad_rate["sampling"]["rate_hz"] = 0
        with self.assertRaisesRegex(engineering.EngineeringProtocolError, "rate_hz"):
            engineering.validate_analysis(bad_rate)

        bad_unit = self.analysis()
        bad_unit["units"]["frequency"] = "V"
        with self.assertRaisesRegex(engineering.EngineeringProtocolError, "frequency unit"):
            engineering.validate_analysis(bad_unit)

        bad_resolution = self.analysis()
        bad_resolution["fft"]["resolution_hz"] = 2.0
        with self.assertRaisesRegex(engineering.EngineeringProtocolError, "resolution"):
            engineering.validate_analysis(bad_resolution)

    def test_aliasing_leakage_and_figure_axes_are_mandatory_checks(self) -> None:
        for check in ("aliasing", "leakage", "figure_axes"):
            with self.subTest(check=check):
                payload = self.analysis()
                payload["checks"].pop(check)
                with self.assertRaisesRegex(engineering.EngineeringProtocolError, "checks"):
                    engineering.validate_analysis(payload)

    def test_simulation_requires_seed_and_backend_can_be_not_observed(self) -> None:
        no_seed = self.analysis()
        no_seed["simulation"]["random_seed"] = None
        with self.assertRaisesRegex(engineering.EngineeringProtocolError, "random_seed"):
            engineering.validate_analysis(no_seed)

        matlab = self.analysis()
        matlab["backend"] = {"name": "matlab", "status": "not-observed", "version": ""}
        self.assertEqual(engineering.validate_analysis(matlab)["backend"]["status"], "not-observed")

    def test_detects_nyquist_aliasing_risk_for_declared_signal_frequency(self) -> None:
        payload = self.analysis()
        payload["sampling"]["max_signal_frequency_hz"] = 600.0
        with self.assertRaisesRegex(engineering.EngineeringProtocolError, "aliasing"):
            engineering.validate_analysis(payload)

    def test_doctor_fail_closes_then_accepts_exact_core(self) -> None:
        blocked = subprocess.run(
            [sys.executable, str(SCRIPT), "doctor"], text=True, encoding="utf-8", capture_output=True
        )
        self.assertEqual(blocked.returncode, 2)
        self.assertEqual(json.loads(blocked.stdout)["status"], "blocked")
        passed = subprocess.run(
            [sys.executable, str(SCRIPT), "doctor", "--core-root", str(ROOT / "plugins" / "deepscientist-lite-core")],
            text=True, encoding="utf-8", capture_output=True,
        )
        self.assertEqual(passed.returncode, 0, passed.stdout + passed.stderr)
        self.assertEqual(json.loads(passed.stdout)["status"], "passed")


if __name__ == "__main__":
    unittest.main()
