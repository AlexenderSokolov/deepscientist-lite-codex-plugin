from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "teaching"))

import host_acceptance  # noqa: E402


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


class HostAcceptanceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="ds-lite-host-acceptance-"))

    def test_hook_summary_requires_real_host_sequence_and_keeps_relative_refs(self) -> None:
        events = self.root / "host" / "hook-events"
        sequence = (
            ("001.json", "user-prompt-submit", "allow"),
            ("002.json", "pre-tool-use", "block"),
            ("003.json", "post-tool-use", "allow"),
            ("004.json", "stop", "block"),
            ("005.json", "stop", "allow"),
        )
        for name, event_type, decision in sequence:
            _write_json(
                events / name,
                {
                    "schema_version": "ds-lite.hook-host-event.v1",
                    "event_type": event_type,
                    "decision": decision,
                },
            )

        result = host_acceptance.summarize_hook_receipts(self.root, events)

        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["host_loading"], "verified")
        self.assertEqual(result["stop_continuation_count"], 1)
        self.assertEqual(len(result["events"]), 5)
        self.assertTrue(all(not Path(item["evidence_ref"]).is_absolute() for item in result["events"]))
        self.assertNotIn(str(self.root), json.dumps(result))

    def test_hook_summary_rejects_fake_host_labels_or_missing_stop_guard(self) -> None:
        events = self.root / "host" / "hook-events"
        _write_json(
            events / "001.json",
            {
                "schema_version": "ds-lite.hook-host-event.v1",
                "event_type": "stop",
                "decision": "block",
                "host_kind": "fake",
            },
        )
        with self.assertRaises(host_acceptance.HostAcceptanceError):
            host_acceptance.summarize_hook_receipts(self.root, events)

    def test_delegation_audit_requires_two_receivers_results_and_one_parent_integration(self) -> None:
        result_refs = [
            "research/worker-a/result.md",
            "research/worker-b/result.md",
        ]
        for ref in result_refs:
            path = self.root / ref
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("bounded child result\n", encoding="utf-8")
        integration_ref = "research/integration.md"
        (self.root / integration_ref).write_text("parent integration\n", encoding="utf-8")
        delegation = {
            "schema_version": "ds-lite.delegation.v1",
            "delegation_id": "real-delegation-01",
            "parent_work_unit_id": "work-real-01",
            "strategy": "parallel",
            "status": "completed",
            "approval": {
                "status": "approved",
                "authority": "user",
                "approval_ref": "research/approval.md",
                "extensions": {},
            },
            "integration_owner": "parent-worker",
            "max_children": 2,
            "nested_delegation": False,
            "tasks": [
                {
                    "task_id": "worker-a",
                    "objective": "Produce A.",
                    "input_refs": ["PROJECT.md"],
                    "allowed_paths": ["research/worker-a/result.md"],
                    "expected_output_refs": [result_refs[0]],
                    "validation_commands": ["test -f research/worker-a/result.md"],
                    "resource_limits": [{"dimension": "walltime", "unit": "minute", "value": 5}],
                    "stop_conditions": ["Stop after one result."],
                    "status": "completed",
                    "result_ref": result_refs[0],
                    "extensions": {},
                },
                {
                    "task_id": "worker-b",
                    "objective": "Produce B.",
                    "input_refs": ["PROJECT.md"],
                    "allowed_paths": ["research/worker-b/result.md"],
                    "expected_output_refs": [result_refs[1]],
                    "validation_commands": ["test -f research/worker-b/result.md"],
                    "resource_limits": [{"dimension": "walltime", "unit": "minute", "value": 5}],
                    "stop_conditions": ["Stop after one result."],
                    "status": "completed",
                    "result_ref": result_refs[1],
                    "extensions": {},
                },
            ],
            "created_at": "2026-07-20T00:00:00Z",
            "updated_at": "2026-07-20T00:10:00Z",
            "extensions": {},
        }
        execution = {
            "status": "completed",
            "extensions": {
                "event_summary": {
                    "collaboration": {
                        "spawn_count": 2,
                        "receiver_count": 2,
                        "receiver_id_sha256": ["a" * 64, "b" * 64],
                        "tool_counts": {"spawn_agent": 2, "wait": 1},
                        "status_counts": {"completed": 3},
                    }
                }
            },
        }
        integration_receipt = self.root / "research" / "integration-receipt.json"
        _write_json(
            integration_receipt,
            {
                "schema_version": "ds-lite.parent-integration.v1",
                "integration_owner": "parent-worker",
                "integration_ref": integration_ref,
                "result_refs": result_refs,
            },
        )

        result = host_acceptance.audit_delegation(
            self.root,
            execution=execution,
            delegation=delegation,
            integration_receipt_path=integration_receipt,
        )

        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["receiver_count"], 2)
        self.assertEqual(result["independent_result_ref_count"], 2)
        self.assertEqual(result["parent_integration_count"], 1)
        self.assertTrue(result["protocol_paths_mutually_exclusive"])
        self.assertFalse(result["os_path_isolation_claimed"])


if __name__ == "__main__":
    unittest.main()
