from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from string import Template

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = REPO_ROOT / "plugins" / "deepscientist-lite" / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import ds_lite_protocol

FACTOR_CARD_TEMPLATE = (
    REPO_ROOT
    / "plugins"
    / "deepscientist-lite"
    / "assets"
    / "templates"
    / "research"
    / "artifacts"
    / "factor-card.json"
)
PROTOCOL_SCRIPT = SCRIPT_DIR / "ds_lite_protocol.py"


class ProtocolSchemaTests(unittest.TestCase):
    def factor_card(self) -> dict:
        factors = []
        for name in (
            "novelty",
            "feasibility",
            "evidence_strength",
            "cost",
            "risk",
            "alignment",
        ):
            factors.append(
                {
                    "name": name,
                    "score": 2,
                    "confidence": "medium",
                    "evidence_refs": [f"research/artifacts/{name}-basis.md"],
                    "summary": f"Recorded basis for {name}.",
                    "uncertainty": ["One bounded pilot remains."],
                    "extensions": {},
                }
            )
        return {
            "schema_version": "ds-lite.factor-card.v1",
            "factor_card_id": "factor-card-route-a",
            "work_unit_id": "work-route-a",
            "profile_id": "core-research-idea",
            "subject_ref": "research/artifacts/idea-route-a.md",
            "status": "assessed",
            "factors": factors,
            "decision": "verify-first",
            "minimal_test": {
                "question": "Does the idea preserve the expected signal under a bounded check?",
                "method": "Run the smallest matched comparison and retain negative results.",
                "expected_evidence": ["A typed result and a reproducible command."],
                "resource_limits": [{"dimension": "walltime", "unit": "minute", "value": 10}],
                "stop_condition": "Stop after one comparison or any authorization blocker.",
                "extensions": {},
            },
            "created_at": "2026-07-17T00:00:00Z",
            "updated_at": "2026-07-17T00:00:00Z",
            "extensions": {},
        }

    def test_factor_card_accepts_complete_object_and_extensions(self) -> None:
        payload = self.factor_card()
        payload["extensions"] = {"future": {"calibration_ref": "research/artifacts/calibration.md"}}
        validated = ds_lite_protocol.validate_factor_card(payload)
        self.assertEqual(validated, payload)

    def test_factor_card_rejects_missing_field(self) -> None:
        payload = self.factor_card()
        payload.pop("decision")
        with self.assertRaisesRegex(ds_lite_protocol.ProtocolError, "missing fields: decision"):
            ds_lite_protocol.validate_factor_card(payload)

    def test_factor_card_rejects_wrong_enum(self) -> None:
        payload = self.factor_card()
        payload["decision"] = "auto-publish"
        with self.assertRaisesRegex(ds_lite_protocol.ProtocolError, "decision"):
            ds_lite_protocol.validate_factor_card(payload)

    def test_factor_card_rejects_path_escape(self) -> None:
        payload = self.factor_card()
        payload["subject_ref"] = "../private/idea.md"
        with self.assertRaisesRegex(ds_lite_protocol.ProtocolError, "subject_ref"):
            ds_lite_protocol.validate_factor_card(payload)

    def test_factor_card_rejects_sensitive_or_hidden_reasoning_fields(self) -> None:
        payload = self.factor_card()
        payload["extensions"] = {"chain_of_thought": "do not retain"}
        with self.assertRaisesRegex(ds_lite_protocol.ProtocolError, "hidden-reasoning"):
            ds_lite_protocol.validate_factor_card(payload)

    def test_factor_card_rejects_id_and_factor_conflicts(self) -> None:
        payload = self.factor_card()
        payload["factor_card_id"] = payload["work_unit_id"]
        with self.assertRaisesRegex(ds_lite_protocol.ProtocolError, "must differ"):
            ds_lite_protocol.validate_factor_card(payload)

        payload = self.factor_card()
        payload["factors"][1]["name"] = "novelty"
        with self.assertRaisesRegex(ds_lite_protocol.ProtocolError, "exactly once"):
            ds_lite_protocol.validate_factor_card(payload)

    def test_factor_card_rejects_unknown_fields_but_allows_extensions(self) -> None:
        payload = self.factor_card()
        payload["weighted_total"] = 3.7
        with self.assertRaisesRegex(ds_lite_protocol.ProtocolError, "unsupported fields: weighted_total"):
            ds_lite_protocol.validate_factor_card(payload)

        payload = self.factor_card()
        payload["extensions"] = {"example.org/calibration": {"version": 1}}
        self.assertEqual(ds_lite_protocol.validate_factor_card(payload), payload)

    def test_factor_card_requires_evidence_for_scored_novelty(self) -> None:
        payload = self.factor_card()
        novelty = payload["factors"][0]
        novelty["evidence_refs"] = []
        with self.assertRaisesRegex(ds_lite_protocol.ProtocolError, "scored factor requires evidence_refs"):
            ds_lite_protocol.validate_factor_card(payload)

        novelty["score"] = None
        novelty["confidence"] = "unknown"
        self.assertEqual(ds_lite_protocol.validate_factor_card(payload), payload)

    def test_factor_card_template_renders_to_valid_object(self) -> None:
        rendered = Template(FACTOR_CARD_TEMPLATE.read_text(encoding="utf-8")).substitute(
            factor_card_id="factor-card-template",
            work_unit_id="work-template",
            profile_id="core-research-idea",
            subject_ref="research/artifacts/idea-template.md",
            created_at="2026-07-17T00:00:00Z",
            updated_at="2026-07-17T00:00:00Z",
        )
        payload = json.loads(rendered)
        self.assertEqual(ds_lite_protocol.validate_factor_card(payload), payload)

    def test_factor_card_cli_validates_file_and_reports_errors(self) -> None:
        root = Path(tempfile.mkdtemp(prefix="ds-lite-factor-card-"))
        path = root / "factor-card.json"
        path.write_text(json.dumps(self.factor_card(), ensure_ascii=False), encoding="utf-8")
        valid = subprocess.run(
            [sys.executable, str(PROTOCOL_SCRIPT), "validate-factor-card", "--path", str(path)],
            text=True,
            encoding="utf-8",
            capture_output=True,
        )
        self.assertEqual(valid.returncode, 0, valid.stdout + valid.stderr)
        self.assertEqual(json.loads(valid.stdout)["schema_version"], "ds-lite.factor-card.v1")

        payload = self.factor_card()
        payload["decision"] = "auto-publish"
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        invalid = subprocess.run(
            [sys.executable, str(PROTOCOL_SCRIPT), "validate-factor-card", "--path", str(path)],
            text=True,
            encoding="utf-8",
            capture_output=True,
        )
        self.assertNotEqual(invalid.returncode, 0)
        self.assertIn("decision", json.loads(invalid.stdout)["error"])


if __name__ == "__main__":
    unittest.main()
