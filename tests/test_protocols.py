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
DELEGATION_TEMPLATE = (
    REPO_ROOT
    / "plugins"
    / "deepscientist-lite"
    / "assets"
    / "templates"
    / "research"
    / "delegation.json"
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

    def delegation(self) -> dict:
        return {
            "schema_version": "ds-lite.delegation.v1",
            "delegation_id": "delegation-pilot",
            "parent_work_unit_id": "work-pilot",
            "strategy": "parallel",
            "status": "authorized",
            "approval": {
                "status": "approved",
                "authority": "user",
                "approval_ref": "research/artifacts/delegation-approval.md",
                "extensions": {},
            },
            "integration_owner": "parent-worker",
            "max_children": 3,
            "nested_delegation": False,
            "tasks": [
                {
                    "task_id": "task-docs",
                    "objective": "Audit the user-facing documentation.",
                    "input_refs": ["PROJECT.md"],
                    "allowed_paths": ["docs/user-guide.zh.md"],
                    "expected_output_refs": ["research/artifacts/delegation-result-task-docs.md"],
                    "validation_commands": ["python tools/validation/validate_repo.py"],
                    "resource_limits": [{"dimension": "walltime", "unit": "minute", "value": 10}],
                    "stop_conditions": ["Stop after the scoped documentation audit."],
                    "status": "authorized",
                    "result_ref": "",
                    "extensions": {},
                },
                {
                    "task_id": "task-tests",
                    "objective": "Audit the protocol regression tests.",
                    "input_refs": ["tests/test_protocols.py"],
                    "allowed_paths": ["tests/test_protocols.py"],
                    "expected_output_refs": ["research/artifacts/delegation-result-task-tests.md"],
                    "validation_commands": ["python tests/test_protocols.py -v"],
                    "resource_limits": [{"dimension": "walltime", "unit": "minute", "value": 10}],
                    "stop_conditions": ["Stop after one bounded test audit."],
                    "status": "authorized",
                    "result_ref": "",
                    "extensions": {},
                },
            ],
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

    def test_delegation_accepts_bounded_object_and_extensions(self) -> None:
        payload = self.delegation()
        payload["extensions"] = {"example.org/transport": {"version": 1}}
        self.assertEqual(ds_lite_protocol.validate_delegation(payload), payload)

    def test_delegation_rejects_missing_field(self) -> None:
        payload = self.delegation()
        payload.pop("integration_owner")
        with self.assertRaisesRegex(ds_lite_protocol.ProtocolError, "missing fields: integration_owner"):
            ds_lite_protocol.validate_delegation(payload)

    def test_delegation_rejects_wrong_enum(self) -> None:
        payload = self.delegation()
        payload["strategy"] = "queue"
        with self.assertRaisesRegex(ds_lite_protocol.ProtocolError, "strategy"):
            ds_lite_protocol.validate_delegation(payload)

    def test_delegation_rejects_path_escape(self) -> None:
        payload = self.delegation()
        payload["tasks"][0]["allowed_paths"] = ["../shared"]
        with self.assertRaisesRegex(ds_lite_protocol.ProtocolError, "allowed_paths"):
            ds_lite_protocol.validate_delegation(payload)

    def test_delegation_rejects_sensitive_or_hidden_reasoning_fields(self) -> None:
        payload = self.delegation()
        payload["tasks"][0]["extensions"] = {"api_key": "not-allowed"}
        with self.assertRaisesRegex(ds_lite_protocol.ProtocolError, "sensitive or hidden-reasoning"):
            ds_lite_protocol.validate_delegation(payload)

    def test_delegation_rejects_id_conflicts(self) -> None:
        payload = self.delegation()
        payload["delegation_id"] = payload["parent_work_unit_id"]
        with self.assertRaisesRegex(ds_lite_protocol.ProtocolError, "must differ"):
            ds_lite_protocol.validate_delegation(payload)

        payload = self.delegation()
        payload["tasks"][1]["task_id"] = payload["tasks"][0]["task_id"]
        with self.assertRaisesRegex(ds_lite_protocol.ProtocolError, "duplicate task_id"):
            ds_lite_protocol.validate_delegation(payload)

        payload = self.delegation()
        payload["integration_owner"] = payload["tasks"][0]["task_id"]
        with self.assertRaisesRegex(ds_lite_protocol.ProtocolError, "integration_owner"):
            ds_lite_protocol.validate_delegation(payload)

        for conflicting_id in (payload["delegation_id"], payload["parent_work_unit_id"]):
            payload = self.delegation()
            payload["tasks"][0]["task_id"] = conflicting_id
            with self.assertRaisesRegex(ds_lite_protocol.ProtocolError, "task_id must differ"):
                ds_lite_protocol.validate_delegation(payload)

    def test_delegation_rejects_unknown_fields_but_allows_extensions(self) -> None:
        payload = self.delegation()
        payload["scheduler"] = "background"
        with self.assertRaisesRegex(ds_lite_protocol.ProtocolError, "unsupported fields: scheduler"):
            ds_lite_protocol.validate_delegation(payload)

        payload = self.delegation()
        payload["tasks"][0]["extensions"] = {"example.org/worker": {"kind": "bounded"}}
        self.assertEqual(ds_lite_protocol.validate_delegation(payload), payload)

    def test_delegation_extensions_cannot_add_runtime_services_or_retry(self) -> None:
        for forbidden in (
            "daemon",
            "queue",
            "scheduler",
            "background_worker",
            "retry",
            "auto_retry",
            "automatic_retry",
            "retry_policy",
            "example.org/scheduler",
            "example.org/auto-retry",
        ):
            with self.subTest(forbidden=forbidden):
                payload = self.delegation()
                payload["extensions"] = {forbidden: True}
                with self.assertRaisesRegex(ds_lite_protocol.ProtocolError, "runtime service or retry"):
                    ds_lite_protocol.validate_delegation(payload)

    def test_delegation_terminal_status_must_match_terminal_tasks(self) -> None:
        payload = self.delegation()
        payload["status"] = "completed"
        with self.assertRaisesRegex(ds_lite_protocol.ProtocolError, "terminal delegation requires terminal tasks"):
            ds_lite_protocol.validate_delegation(payload)

        for task in payload["tasks"]:
            task["status"] = "completed"
            task["result_ref"] = task["expected_output_refs"][0]
        self.assertEqual(ds_lite_protocol.validate_delegation(payload), payload)

    def test_delegation_rejects_capacity_nested_and_path_overlap(self) -> None:
        payload = self.delegation()
        payload["max_children"] = 4
        with self.assertRaisesRegex(ds_lite_protocol.ProtocolError, "max_children"):
            ds_lite_protocol.validate_delegation(payload)

        payload = self.delegation()
        payload["nested_delegation"] = True
        with self.assertRaisesRegex(ds_lite_protocol.ProtocolError, "nested_delegation must be false"):
            ds_lite_protocol.validate_delegation(payload)

        payload = self.delegation()
        payload["tasks"][0]["allowed_paths"] = ["docs"]
        payload["tasks"][1]["allowed_paths"] = ["docs/user-guide.zh.md"]
        with self.assertRaisesRegex(ds_lite_protocol.ProtocolError, "overlapping allowed_paths"):
            ds_lite_protocol.validate_delegation(payload)

    def test_delegation_requires_approval_before_active_states(self) -> None:
        payload = self.delegation()
        payload["approval"] = {"status": "required", "authority": "none", "approval_ref": "", "extensions": {}}
        with self.assertRaisesRegex(ds_lite_protocol.ProtocolError, "requires approved authorization"):
            ds_lite_protocol.validate_delegation(payload)

    def test_delegation_terminal_task_requires_result_ref(self) -> None:
        payload = self.delegation()
        payload["tasks"][0]["status"] = "completed"
        with self.assertRaisesRegex(ds_lite_protocol.ProtocolError, "terminal task requires result_ref"):
            ds_lite_protocol.validate_delegation(payload)

        payload["tasks"][0]["result_ref"] = "research/artifacts/delegation-result-task-docs.md"
        self.assertEqual(ds_lite_protocol.validate_delegation(payload), payload)

    def test_delegation_template_renders_to_valid_planned_object(self) -> None:
        rendered = Template(DELEGATION_TEMPLATE.read_text(encoding="utf-8")).substitute(
            delegation_id="delegation-template",
            parent_work_unit_id="work-template",
            integration_owner="parent-worker",
            created_at="2026-07-17T00:00:00Z",
            updated_at="2026-07-17T00:00:00Z",
        )
        payload = json.loads(rendered)
        self.assertEqual(ds_lite_protocol.validate_delegation(payload), payload)

    def test_delegation_cli_validates_file_and_reports_errors(self) -> None:
        root = Path(tempfile.mkdtemp(prefix="ds-lite-delegation-"))
        path = root / "delegation.json"
        path.write_text(json.dumps(self.delegation(), ensure_ascii=False), encoding="utf-8")
        valid = subprocess.run(
            [sys.executable, str(PROTOCOL_SCRIPT), "validate-delegation", "--path", str(path)],
            text=True,
            encoding="utf-8",
            capture_output=True,
        )
        self.assertEqual(valid.returncode, 0, valid.stdout + valid.stderr)
        self.assertEqual(json.loads(valid.stdout)["schema_version"], "ds-lite.delegation.v1")

        payload = self.delegation()
        payload["nested_delegation"] = True
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        invalid = subprocess.run(
            [sys.executable, str(PROTOCOL_SCRIPT), "validate-delegation", "--path", str(path)],
            text=True,
            encoding="utf-8",
            capture_output=True,
        )
        self.assertNotEqual(invalid.returncode, 0)
        self.assertIn("nested_delegation", json.loads(invalid.stdout)["error"])


if __name__ == "__main__":
    unittest.main()
