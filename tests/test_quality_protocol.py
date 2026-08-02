from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "plugins" / "deepscientist-lite-core" / "scripts" / "ds_lite_quality.py"


class QualityProtocolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="ds-lite-quality-"))

    def run_cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run([sys.executable, str(SCRIPT), *args], cwd=REPO_ROOT, text=True, encoding="utf-8", capture_output=True)

    def test_medium_plan_requires_requirements_tests_coverage_and_risk(self) -> None:
        result = self.run_cli(
            "validate-plan", "--path", str(self.root / "missing.json"),
        )
        self.assertNotEqual(result.returncode, 0)
        plan = self.root / "plan.json"
        plan.write_text(json.dumps({
            "schema_version": "ds-lite.quality-plan.v1", "plan_id": "q1", "risk": "medium",
            "requirements": ["R1"], "allowed_paths": ["src"], "authorization_ref": "approval/q1.md",
            "metrics": ["correctness"], "acceptance": ["tests pass"], "test_strategy": ["unit", "gherkin", "coverage"],
            "rollback": "revert", "residual_risks": ["provider unavailable"], "extensions": {},
        }, indent=2), encoding="utf-8")
        result = self.run_cli("validate-plan", "--path", str(plan))
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_high_result_blocks_when_mutation_and_fresh_review_are_missing(self) -> None:
        result = self.run_cli("evaluate-result", "--path", str(self.root / "result.json"))
        self.assertNotEqual(result.returncode, 0)
        result_path = self.root / "result.json"
        result_path.write_text(json.dumps({
            "schema_version": "ds-lite.quality-result.v1", "plan_id": "q1", "status": "passed", "risk": "high",
            "requirement_trace": [{"id": "R1", "status": "passed", "evidence": ["tests/test.py"]}],
            "security": {"status": "passed", "evidence": ["review/security.md"]},
            "tests": {"status": "passed", "commands": ["pytest -q"], "gherkin": "passed"},
            "coverage": {"changed_lines": 95, "threshold": 90},
            "mutation": {"score": 80, "threshold": 80},
            "recovery": {"status": "passed"}, "review": {"fresh_reviewer": "passed", "adjudicator": "passed"},
            "residual_risks": [], "extensions": {},
        }, indent=2), encoding="utf-8")
        result = self.run_cli("evaluate-result", "--path", str(result_path))
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
