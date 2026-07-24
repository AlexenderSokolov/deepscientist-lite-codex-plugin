from __future__ import annotations

import sys
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "plugins" / "deepscientist-lite" / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import ds_lite_protocol


def delegation_payload() -> dict:
    task = lambda task_id, path: {
        "task_id": task_id,
        "objective": f"Inspect {task_id}.",
        "input_refs": ["PROJECT.md"],
        "allowed_paths": [path],
        "expected_output_refs": [f"research/artifacts/{task_id}-result.md"],
        "validation_commands": ["python tools/validation/validate_repo.py"],
        "resource_limits": [{"dimension": "walltime", "unit": "minute", "value": 5}],
        "stop_conditions": ["Stop after one bounded inspection."],
        "status": "authorized",
        "result_ref": "",
        "extensions": {},
    }
    return {
        "schema_version": "ds-lite.delegation.v1",
        "delegation_id": "delegation-probe",
        "parent_work_unit_id": "work-probe",
        "strategy": "parallel",
        "status": "authorized",
        "approval": {
            "status": "approved",
            "authority": "user",
            "approval_ref": "research/artifacts/delegation-approval.md",
            "extensions": {},
        },
        "integration_owner": "parent-worker",
        "max_children": 2,
        "nested_delegation": False,
        "tasks": [
            task("worker-a", "research/artifacts/worker-a-result.md"),
            task("worker-b", "research/artifacts/worker-b-result.md"),
        ],
        "created_at": "2026-07-20T00:00:00Z",
        "updated_at": "2026-07-20T00:00:00Z",
        "extensions": {},
    }


class DelegationProbeTests(unittest.TestCase):
    def test_parallel_plan_has_mutually_exclusive_paths_and_single_owner(self):
        payload = delegation_payload()
        validated = ds_lite_protocol.validate_delegation(payload)
        self.assertEqual(validated["integration_owner"], "parent-worker")
        self.assertFalse(validated["nested_delegation"])
        self.assertEqual(len(validated["tasks"]), 2)

    def test_overlapping_paths_are_rejected_before_host_execution(self):
        payload = delegation_payload()
        payload["tasks"][1]["allowed_paths"] = ["research/artifacts/worker-a-result.md"]
        with self.assertRaisesRegex(ds_lite_protocol.ProtocolError, "overlapping"):
            ds_lite_protocol.validate_delegation(payload)

    def test_terminal_child_without_result_ref_is_rejected(self):
        payload = delegation_payload()
        payload["tasks"][0]["status"] = "completed"
        with self.assertRaisesRegex(ds_lite_protocol.ProtocolError, "result_ref"):
            ds_lite_protocol.validate_delegation(payload)

    def test_plan_without_approval_cannot_be_authorized(self):
        payload = delegation_payload()
        payload["approval"] = {"status": "required", "authority": "none", "approval_ref": "", "extensions": {}}
        payload["status"] = "planned"
        self.assertEqual(ds_lite_protocol.validate_delegation(payload)["status"], "planned")
        payload["status"] = "authorized"
        with self.assertRaisesRegex(ds_lite_protocol.ProtocolError, "approved"):
            ds_lite_protocol.validate_delegation(payload)


if __name__ == "__main__":
    unittest.main()
