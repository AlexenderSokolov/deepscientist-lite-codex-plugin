import json
import os
import tempfile
import unittest
import uuid
from pathlib import Path

from plugins.deepscientist_lite_import_shim import ds_lite_autoresearch_runner


REPO_ROOT = Path(__file__).resolve().parents[1]


class AutoresearchRunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        writable_root = Path(os.environ.get(
            "DS_LITE_TEST_ROOT",
            os.environ.get("TEMP_ROOT", str(REPO_ROOT / ".tmp-test-artifacts")),
        ))
        # Python's mkdtemp creates a 0700 directory. The managed Windows
        # runner assigns that ACL to a different sandbox identity, so use an
        # explicit project-owned directory for this test fixture.
        self.root = writable_root / f"ds-lite-autoresearch-runner-{uuid.uuid4().hex[:12]}"
        self.root.mkdir(parents=True, exist_ok=False)

    def tearDown(self) -> None:
        # Keep isolated evidence directories for post-test inspection.
        pass

    def test_completion_requires_report_for_every_frozen_goal(self) -> None:
        result = ds_lite_autoresearch_runner.inspect_completion(
            "<completion_report>\n- [x] source\n</completion_report>\nCONFIRMED: all tasks completed",
            ["source", "release"],
        )
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["missing_goals"], ["release"])
        self.assertEqual(result["failure_layer"], "completion-report-incomplete")

    def test_build_command_switches_to_same_session_resume(self) -> None:
        initial = ds_lite_autoresearch_runner.build_codex_command(
            "codex", self.root, "initial prompt", None, "workspace-write"
        )
        resumed = ds_lite_autoresearch_runner.build_codex_command(
            "codex", self.root, "continue", "session-123", "workspace-write"
        )
        self.assertEqual(initial[:2], ["codex", "exec"])
        self.assertIn("initial prompt", initial)
        self.assertEqual(resumed[:3], ["codex", "exec", "resume"])
        self.assertIn("session-123", resumed)

    def test_second_owner_is_rejected_without_removing_owner_record(self) -> None:
        state_dir = self.root / "job"
        first = ds_lite_autoresearch_runner.claim_owner(state_dir, "owner-a", now=100, lease_seconds=60)
        self.assertTrue(first)
        self.assertFalse(ds_lite_autoresearch_runner.claim_owner(state_dir, "owner-b", now=101, lease_seconds=60))
        owner = json.loads((state_dir / "owner.json").read_text(encoding="utf-8"))
        self.assertEqual(owner["owner_id"], "owner-a")
        self.assertTrue((state_dir / "owner.json").is_file())

    def test_expired_owner_reclaim_is_serialized_and_preserves_new_owner(self) -> None:
        state_dir = self.root / "expired-job"
        self.assertTrue(ds_lite_autoresearch_runner.claim_owner(state_dir, "owner-a", now=100, lease_seconds=1))
        self.assertTrue(ds_lite_autoresearch_runner.claim_owner(state_dir, "owner-b", now=102, lease_seconds=60))
        self.assertFalse(ds_lite_autoresearch_runner.claim_owner(state_dir, "owner-c", now=103, lease_seconds=60))
        owner = json.loads((state_dir / "owner.json").read_text(encoding="utf-8"))
        self.assertEqual(owner["owner_id"], "owner-b")
        self.assertTrue(owner["active"])

    def test_budget_exhaustion_is_needs_resume_and_keeps_session(self) -> None:
        calls = []

        def executor(command, prompt):
            calls.append((command, prompt))
            return {"session_id": "session-1", "message": "not complete", "failure_layer": "none"}

        result = ds_lite_autoresearch_runner.run_job(
            root=self.root,
            job_id="job-1",
            initial_prompt="do work",
            frozen_goals=["source"],
            executor=executor,
            max_attempts=1,
            lease_seconds=60,
            owner_id="owner-a",
            state_dir=self.root,
        )
        self.assertEqual(result["status"], "needs_resume")
        self.assertEqual(result["session_id"], "session-1")
        self.assertEqual(len(calls), 1)
        self.assertFalse((self.root / "summary.json").exists())
        self.assertTrue((self.root / "completion-failure-0001.json").is_file())
        failure = json.loads((self.root / "completion-failure-0001.json").read_text(encoding="utf-8"))
        self.assertIn("completion_failure_prompt", failure)
        self.assertIn("source", failure["completion_failure_prompt"])

    def test_resume_uses_persisted_session_and_writes_structured_artifacts(self) -> None:
        first_calls = []

        def first_executor(command, prompt):
            first_calls.append((command, prompt))
            return {"session_id": "session-1", "message": "unfinished private output", "failure_layer": "none"}

        first = ds_lite_autoresearch_runner.run_job(
            root=self.root,
            job_id="job-2",
            initial_prompt="do work",
            frozen_goals=["source"],
            executor=first_executor,
            max_attempts=1,
            owner_id="owner-a",
            state_dir=self.root / "job-2",
        )
        self.assertEqual(first["status"], "needs_resume")

        second_calls = []

        def second_executor(command, prompt):
            second_calls.append((command, prompt))
            return {
                "session_id": "session-1",
                "message": "<completion_report>\n- [x] source\n</completion_report>\nCONFIRMED: all tasks completed",
                "failure_layer": "none",
            }

        second = ds_lite_autoresearch_runner.run_job(
            root=self.root,
            job_id="job-2",
            initial_prompt="ignored on resume",
            frozen_goals=[],
            executor=second_executor,
            max_attempts=1,
            owner_id="owner-b",
            state_dir=self.root / "job-2",
        )
        self.assertEqual(second["status"], "completed")
        self.assertEqual(second_calls[0][0][:3], ["codex", "exec", "resume"])
        self.assertIn("session-1", second_calls[0][0])
        self.assertTrue((self.root / "job-2" / "session-id.txt").is_file())
        self.assertTrue((self.root / "job-2" / "last-message.txt").is_file())
        self.assertEqual(len((self.root / "job-2" / "events.jsonl").read_text(encoding="utf-8").splitlines()), 2)
        self.assertNotIn("unfinished private output", (self.root / "job-2" / "last-message.txt").read_text(encoding="utf-8"))
        self.assertNotIn("unfinished private output", (self.root / "job-2" / "events.jsonl").read_text(encoding="utf-8"))

    def test_user_action_and_non_retryable_failure_do_not_auto_resume(self) -> None:
        awaiting = ds_lite_autoresearch_runner.run_job(
            root=self.root,
            job_id="job-3",
            initial_prompt="do work",
            frozen_goals=["source"],
            executor=lambda command, prompt: {
                "status": "awaiting_user_action",
                "failure_layer": "provider-authorization",
                "next_automatic_action": "await-provider-authorization",
            },
            max_attempts=3,
            owner_id="owner-a",
            state_dir=self.root / "job-3",
        )
        self.assertEqual(awaiting["status"], "awaiting_user_action")
        self.assertEqual(awaiting["next_automatic_action"], "await-provider-authorization")

        failed = ds_lite_autoresearch_runner.run_job(
            root=self.root,
            job_id="job-4",
            initial_prompt="do work",
            frozen_goals=["source"],
            executor=lambda command, prompt: {
                "status": "failed",
                "failure_layer": "session-drift",
                "retryable": False,
            },
            max_attempts=3,
            owner_id="owner-a",
            state_dir=self.root / "job-4",
        )
        self.assertEqual(failed["status"], "failed")
        self.assertEqual(failed["next_automatic_action"], "freeze-identity-and-diagnose")

    def test_quota_failure_waits_for_user_and_records_only_recovery_metadata(self) -> None:
        result = ds_lite_autoresearch_runner.run_job(
            root=self.root, job_id="quota-wait", initial_prompt="do work", frozen_goals=["provider"],
            executor=lambda command, prompt: {"session_id": "session-quota", "failure_layer": "provider", "http_status": 402, "message": "quota exhausted"},
            max_attempts=3, owner_id="owner-a", state_dir=self.root / "quota-wait",
        )
        self.assertEqual(result["status"], "awaiting_user_action")
        attempt = json.loads((self.root / "quota-wait" / "attempt-0001.json").read_text(encoding="utf-8"))
        self.assertEqual(attempt["recovery"]["recovery_class"], "awaiting-user-action")
        self.assertNotIn("quota exhausted", json.dumps(attempt))

    def test_retryable_http_failure_keeps_same_session_for_watch(self) -> None:
        calls = []
        def executor(command, prompt):
            calls.append(command)
            if len(calls) == 1:
                return {"session_id": "session-http", "failure_layer": "provider", "http_status": 503, "message": "temporary failure"}
            return {"session_id": "session-http", "message": "<completion_report>\n- [x] source\n</completion_report>\nCONFIRMED: all tasks completed", "failure_layer": "none"}
        result = ds_lite_autoresearch_runner.watch_job(root=self.root, job_id="http-watch", initial_prompt="do work", frozen_goals=["source"], executor=executor, max_attempts=1, owner_id="owner-a", state_dir=self.root / "http-watch")
        self.assertEqual(result["status"], "completed")
        self.assertEqual(calls[1][:3], ["codex", "exec", "resume"])

    def test_watch_resumes_same_session_until_completed(self) -> None:
        calls = []

        def executor(command, prompt):
            calls.append((command, prompt))
            if len(calls) < 3:
                return {"session_id": "session-watch", "message": "unfinished", "failure_layer": "none"}
            return {
                "session_id": "session-watch",
                "message": "<completion_report>\n- [x] source\n</completion_report>\nCONFIRMED: all tasks completed",
                "failure_layer": "none",
            }

        result = ds_lite_autoresearch_runner.watch_job(
            root=self.root,
            job_id="watch-job",
            initial_prompt="do work",
            frozen_goals=["source"],
            executor=executor,
            max_attempts=1,
            owner_id="watch-owner",
            state_dir=self.root / "watch-job",
        )
        self.assertEqual(result["status"], "completed")
        self.assertEqual(len(calls), 3)
        self.assertEqual(calls[0][0][:2], ["codex", "exec"])
        self.assertEqual(calls[1][0][:3], ["codex", "exec", "resume"])

    def test_watch_batch_limit_preserves_needs_resume(self) -> None:
        result = ds_lite_autoresearch_runner.watch_job(
            root=self.root,
            job_id="watch-limited",
            initial_prompt="do work",
            frozen_goals=["source"],
            executor=lambda command, prompt: {
                "session_id": "session-limited",
                "message": "unfinished",
                "failure_layer": "none",
            },
            max_attempts=1,
            max_batches=1,
            owner_id="watch-owner",
            state_dir=self.root / "watch-limited",
        )
        self.assertEqual(result["status"], "needs_resume")

    def test_missing_session_id_fails_closed_without_starting_a_new_session(self) -> None:
        calls = []

        def executor(command, prompt):
            calls.append(command)
            return {"message": "unfinished", "failure_layer": "none"}

        result = ds_lite_autoresearch_runner.run_job(
            root=self.root,
            job_id="missing-session",
            initial_prompt="do work",
            frozen_goals=["source"],
            executor=executor,
            max_attempts=3,
            owner_id="owner-a",
            state_dir=self.root / "missing-session",
        )
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["last_completion"]["failure_layer"], "session-id-not-observed")
        self.assertEqual(len(calls), 1)
        self.assertFalse(any("resume" in command for command in calls))


if __name__ == "__main__":
    unittest.main()
