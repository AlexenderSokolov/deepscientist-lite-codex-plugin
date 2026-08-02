from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / "plugins" / "deepscientist-lite-empirical"
SCRIPT = PACK / "scripts" / "ds_lite_empirical.py"


def load_module():
    spec = importlib.util.spec_from_file_location("ds_lite_empirical", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


empirical = load_module()


class EmpiricalPackTests(unittest.TestCase):
    def spec(self):
        return {
            "schema_version": "ds-lite.empirical-spec.v1",
            "study_id": "study-1",
            "research_question": "What is the effect of treatment on outcome?",
            "estimand": "ATT",
            "population": "Eligible units in the study period",
            "sample": {"inclusion": ["eligible"], "exclusion": ["missing treatment"]},
            "variables": {"outcome": ["y"], "treatment": ["treated"], "covariates": ["x"]},
            "identification_strategy": "difference-in-differences",
            "assumptions": ["parallel-trends", "no-anticipation"],
            "diagnostics": ["pretrend", "missingness"],
            "robustness_plan": ["clustered-standard-errors", "alternative-window"],
            "backend": {"name": "python", "status": "available"},
            "data_refs": ["research/data/analysis.csv"],
            "extensions": {},
        }

    def result(self):
        return {
            "schema_version": "ds-lite.empirical-result.v1",
            "study_id": "study-1",
            "spec_ref": "research/specs/study-1.json",
            "status": "completed",
            "estimate": {"value": 0.0, "uncertainty": "95% CI [-0.2, 0.2]", "unit": "outcome units"},
            "diagnostics": [
                {"name": "pretrend", "status": "failed", "detail": "Lead coefficient differs from zero"},
                {"name": "clustered-standard-errors", "status": "passed", "detail": "Clustered by unit"},
                {"name": "missingness", "status": "warning", "detail": "8% outcome missing"},
            ],
            "robustness": [
                {"name": "alternative-window", "status": "disagrees", "detail": "Sign changes"}
            ],
            "conclusion": "The planned design does not support a positive effect claim.",
            "negative_result": True,
            "evidence_pack_ref": "research/evidence/study-1/evidence-pack.json",
            "commands": ["python analysis/run_did.py"],
            "artifact_refs": ["research/results/study-1.json", "research/figures/event-study.png"],
            "extensions": {},
        }

    def test_spec_is_method_neutral_and_valid(self) -> None:
        self.assertEqual(empirical.validate_spec(self.spec())["estimand"], "ATT")
        stata = self.spec()
        stata["backend"] = {"name": "stata", "status": "not-observed"}
        self.assertEqual(empirical.validate_spec(stata)["backend"]["status"], "not-observed")

    def test_result_preserves_failed_diagnostics_robustness_disagreement_and_null_result(self) -> None:
        validated = empirical.validate_result(self.result())
        self.assertTrue(validated["negative_result"])
        self.assertIn("failed", {item["status"] for item in validated["diagnostics"]})
        self.assertIn("disagrees", {item["status"] for item in validated["robustness"]})

    def test_result_requires_core_evidence_pack_and_rejects_significance_as_conclusion(self) -> None:
        missing = self.result()
        missing["evidence_pack_ref"] = ""
        with self.assertRaisesRegex(empirical.EmpiricalProtocolError, "evidence_pack_ref"):
            empirical.validate_result(missing)

        bad = self.result()
        bad["conclusion"] = "The result is significant, therefore the theory is true."
        with self.assertRaisesRegex(empirical.EmpiricalProtocolError, "significance"):
            empirical.validate_result(bad)

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
