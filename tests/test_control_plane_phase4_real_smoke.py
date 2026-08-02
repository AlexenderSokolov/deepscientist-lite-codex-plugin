from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from teaching.controller_phase4_reviewer_smoke import evaluate_wire_evidence


class Phase4RealReviewerSmokeTests(unittest.TestCase):
    def test_wire_evidence_requires_read_only_never_approve_and_denied_canary(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ds-lite-phase4-real-wire-") as directory:
            artifact_root = Path(directory)
            rows = [
                {
                    "direction": "outbound",
                    "request_id": "review-1:thread-start",
                    "method": "thread/start",
                    "frame": {"params": {
                        "cwd": str(artifact_root), "sandbox": "read-only",
                        "approvalPolicy": "never", "model": "gpt-5.6-sol",
                    }},
                },
                {
                    "direction": "outbound",
                    "request_id": "review-1:turn-start",
                    "method": "turn/start",
                    "frame": {"params": {"threadId": "review-thread"}},
                },
                {
                    "direction": "outbound", "request_id": "phase4-canary-thread-start",
                    "method": "thread/start", "frame": {"params": {
                        "cwd": str(artifact_root), "sandbox": "read-only",
                        "approvalPolicy": "never", "model": "gpt-5.6-sol",
                    }},
                },
                {
                    "direction": "outbound", "request_id": "phase4-canary-turn-start",
                    "method": "turn/start", "frame": {"params": {"threadId": "canary-thread"}},
                },
                {
                    "direction": "inbound",
                    "method": "item/completed",
                    "frame": {"params": {"item": {
                        "type": "commandExecution",
                        "command": "echo denied > phase4-write-canary-forbidden.txt",
                        "status": "failed", "exitCode": 1,
                    }}},
                },
            ]

            checks = evaluate_wire_evidence(
                rows, review_id="review-1", artifact_root=artifact_root,
                model="gpt-5.6-sol", worker_thread_id="worker-thread",
                reviewer_thread_id="review-thread",
                canary_name="phase4-write-canary-forbidden.txt",
            )

            self.assertTrue(all(checks.values()))

    def test_wire_evidence_does_not_treat_missing_canary_attempt_as_denied(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ds-lite-phase4-real-wire-missing-") as directory:
            checks = evaluate_wire_evidence(
                [], review_id="review-1", artifact_root=Path(directory),
                model="gpt-5.6-sol", worker_thread_id="worker-thread",
                reviewer_thread_id="review-thread",
                canary_name="phase4-write-canary-forbidden.txt",
            )

            self.assertFalse(checks["write_canary_command_observed"])
            self.assertFalse(checks["write_canary_denied"])


if __name__ == "__main__":
    unittest.main()
