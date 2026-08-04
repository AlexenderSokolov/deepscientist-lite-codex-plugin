from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from tools.validation import matched_effect_candidate_acceptance as acceptance


def write(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


class MatchedEffectCandidateAcceptanceTests(unittest.TestCase):
    def fixture(self, root: Path) -> tuple[Path, Path, Path, Path]:
        core = root / "plugins" / "deepscientist-lite-core"
        write(core / "skill.json", {"stable": True})
        write(core / "THIRD.json", {"notice": True})
        tree_digest = acceptance.tree_digest(core)
        pilot = root / "pilot"
        write(pilot / "source-snapshot" / "SOURCE_IDENTITY.json", {
            "tree_digest": tree_digest, "plugin_version": "0.9.0-beta.1", "skill_count": 9,
        })
        write(pilot / "source-snapshot" / "plugins" / "deepscientist-lite-core" / "skill.json", {"stable": True})
        write(pilot / "source-snapshot" / "plugins" / "deepscientist-lite-core" / "THIRD.json", {"notice": True})
        report = write(pilot / "results" / "matched-effect.json", {
            "schema_version": "ds-lite.matched-effect.v1",
            "status": "descriptive-improvement-supported",
            "case_count": 4, "arm_count": 3, "experimental_call_count": 18,
            "blind_review_complete": True, "blind_review_call_count": 1,
            "mapping_available_to_reviewer": False,
            "decision_checks": {
                "expression_dimensions_favorable_in_both_comparisons": 4,
                "unsupported_completion_not_increased": True,
                "task_correctness_not_materially_worse": True,
            },
        })
        review = write(pilot / "results" / "blind-review-execution.json", {
            "schema_version": "ds-lite.blind-review-execution.v1", "status": "completed",
            "call_count": 1, "mapping_available_to_reviewer": False,
        })
        source_entries = [{
            "path": "plugins/deepscientist-lite-core/" + name,
            "sha256": hashlib.sha256((core / name).read_bytes()).hexdigest(),
            "size": (core / name).stat().st_size,
        } for name in ("THIRD.json", "skill.json")]
        candidate = write(root / "candidate.json", {
            "schema_version": "ds-lite.phase5-release-candidate.v1",
            "candidate_digest": "a" * 64,
            "source_manifest": {"schema_version": "ds-lite.candidate-manifest.v1", "files": source_entries},
        })
        return candidate, pilot, report, review

    def test_passes_only_when_pilot_core_and_candidate_bytes_match(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            candidate, pilot, report, review = self.fixture(root)
            result = acceptance.build_acceptance(
                candidate, root, pilot, report, review, root / "acceptance.json",
            )
            self.assertEqual(result["status"], "passed")
            self.assertEqual(result["candidate_digest"], "a" * 64)
            self.assertTrue(all(result["checks"].values()))
            self.assertFalse(result["release_allowed"])

    def test_candidate_or_pilot_drift_blocks(self) -> None:
        for target in ("current", "snapshot"):
            with self.subTest(target=target), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                candidate, pilot, report, review = self.fixture(root)
                path = (
                    root / "plugins" / "deepscientist-lite-core" / "skill.json"
                    if target == "current"
                    else pilot / "source-snapshot" / "plugins" / "deepscientist-lite-core" / "skill.json"
                )
                path.write_text("drift\n", encoding="utf-8")
                result = acceptance.build_acceptance(
                    candidate, root, pilot, report, review, root / "acceptance.json",
                )
                self.assertEqual(result["status"], "blocked")

    def test_threshold_miss_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            candidate, pilot, report, review = self.fixture(root)
            payload = json.loads(report.read_text(encoding="utf-8"))
            payload["status"] = "mixed"
            payload["decision_checks"]["expression_dimensions_favorable_in_both_comparisons"] = 3
            report.write_text(json.dumps(payload), encoding="utf-8")
            result = acceptance.build_acceptance(
                candidate, root, pilot, report, review, root / "acceptance.json",
            )
            self.assertEqual(result["status"], "blocked")
            self.assertFalse(result["checks"]["effect_thresholds_passed"])

    def test_output_is_write_once(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            candidate, pilot, report, review = self.fixture(root)
            output = root / "acceptance.json"
            acceptance.build_acceptance(candidate, root, pilot, report, review, output)
            before = output.read_bytes()
            with self.assertRaises(FileExistsError):
                acceptance.build_acceptance(candidate, root, pilot, report, review, output)
            self.assertEqual(output.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
