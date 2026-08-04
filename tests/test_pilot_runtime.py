from __future__ import annotations

import inspect
import json
import os
import subprocess
import tempfile
import textwrap
import time
import unittest
from unittest.mock import patch
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "teaching"))

import pilot_runtime  # noqa: E402
import pilot_score  # noqa: E402


class PilotRuntimeEntrypointTests(unittest.TestCase):
    def test_runtime_and_score_entrypoints_exist(self) -> None:
        self.assertTrue((REPO_ROOT / "teaching" / "pilot_runtime.py").is_file())
        self.assertTrue((REPO_ROOT / "teaching" / "pilot_score.py").is_file())

    def test_runtime_exposes_bounded_execution_api(self) -> None:
        for name in (
            "PilotError",
            "PilotProgress",
            "build_progress_context",
            "validate_execution",
            "reduce_event_lines",
            "build_execution_plan",
            "prepare_pilot",
            "install_homes",
            "preflight_pilot",
            "run_canary",
            "resume_decision",
            "run_codex_call",
        ):
            with self.subTest(name=name):
                self.assertTrue(hasattr(pilot_runtime, name), f"missing pilot runtime API: {name}")

    def test_powershell_codex_launcher_uses_explicit_host(self) -> None:
        launcher = Path(r"C:\\isolated\\codex.ps1")
        self.assertEqual(
            pilot_runtime._command_prefix(launcher),
            ["powershell.exe", "-NoProfile", "-File", str(launcher)],
        )

    def test_windows_canary_isolated_from_wsl_only_preflight_block(self) -> None:
        self.assertTrue(
            pilot_runtime._windows_canary_preflight_ready(
                {"status": "blocked", "blocking_reasons": ["wsl-precondition"]}
            )
        )
        self.assertFalse(
            pilot_runtime._windows_canary_preflight_ready(
                {"status": "blocked", "blocking_reasons": ["wsl-precondition", "authentication"]}
            )
        )

    def test_validated_wsl_host_probe_requires_complete_host_evidence(self) -> None:
        root = Path(tempfile.mkdtemp(prefix="ds-lite-wsl-host-probe-"))
        receipt = root / "wsl-host-probe.json"
        receipt.write_text(json.dumps({
            "schema_version": "ds-lite.wsl-host-probe.v1", "status": "passed",
            "host": "windows-powershell", "distribution": "DS-Lite-Ubuntu-24.04",
            "assertion": "uname-s-is-linux", "exit_code": 0,
            "raw_output_persisted": False,
        }), encoding="utf-8")
        self.assertTrue(pilot_runtime._validated_wsl_host_probe(receipt))
        receipt.write_text("\ufeff" + receipt.read_text(encoding="utf-8"), encoding="utf-8")
        self.assertTrue(pilot_runtime._validated_wsl_host_probe(receipt))
        receipt.write_text(json.dumps({"schema_version": "ds-lite.wsl-host-probe.v1", "status": "passed"}), encoding="utf-8")
        self.assertFalse(pilot_runtime._validated_wsl_host_probe(receipt))

    def test_execution_arguments_use_an_absolute_workspace(self) -> None:
        args = pilot_runtime._codex_args(
            {"session_mode": "ephemeral", "call_id": "case-01"},
            Path("research/.validation-tmp/relative-workspace"),
            "",
        )
        workspace = Path(args[args.index("-C") + 1])
        self.assertTrue(workspace.is_absolute())

    def test_numerical_call_uses_call_scoped_wsl_capable_sandbox_only(self) -> None:
        numerical = pilot_runtime._codex_args(
            {"case": "numerical-seeds", "session_mode": "ephemeral", "call_id": "numerical-seeds--plain--r1"},
            Path("research/.validation-tmp/numerical-workspace"),
            "",
        )
        ordinary = pilot_runtime._codex_args(
            {"case": "math-counterexample", "session_mode": "ephemeral", "call_id": "math-counterexample--plain--r1"},
            Path("research/.validation-tmp/math-workspace"),
            "",
        )
        self.assertEqual(numerical[numerical.index("-s") + 1], "danger-full-access")
        self.assertEqual(ordinary[ordinary.index("-s") + 1], "workspace-write")

    def test_stable_resume_uses_exact_session_and_inherits_original_workspace_policy(self) -> None:
        args = pilot_runtime._codex_args(
            {"session_mode": "temporary-resume", "call_id": "case-02"},
            Path("research/.validation-tmp/relative-workspace"),
            "session-123",
        )
        self.assertEqual(args[:2], ["exec", "resume"])
        self.assertNotIn("--last", args)
        self.assertNotIn("-s", args)
        self.assertNotIn("-C", args)
        self.assertEqual(args[-1], "session-123")

    def test_session_cleanup_uses_absolute_home_and_workspace_boundaries(self) -> None:
        root = Path(tempfile.mkdtemp(prefix="ds-lite-pilot-cleanup-"))
        binary = root / "codex.exe"
        home = Path("research/.validation-tmp/relative-home")
        workspace = Path("research/.validation-tmp/relative-workspace")
        with patch.object(
            pilot_runtime.subprocess, "run",
            return_value=type("Completed", (), {"returncode": 0})(),
        ) as run:
            self.assertTrue(
                pilot_runtime._delete_session(binary, home, workspace, "session-123")
            )
        self.assertEqual(run.call_args.kwargs["env"]["CODEX_HOME"], str(home.resolve()))
        self.assertEqual(run.call_args.kwargs["cwd"], workspace.resolve())

    def test_cross_platform_pilot_wrappers_and_validation_lists_exist(self) -> None:
        wrappers = (
            REPO_ROOT / "teaching" / "run_pilot.ps1",
            REPO_ROOT / "teaching" / "run_pilot.sh",
        )
        for wrapper in wrappers:
            with self.subTest(wrapper=wrapper.name):
                self.assertTrue(wrapper.is_file())
                text = wrapper.read_text(encoding="utf-8").lower()
                for command in ("prepare", "install", "preflight", "canary", "run", "resume", "score"):
                    self.assertIn(command, text)
                self.assertNotIn("auth.json", text)
                self.assertNotIn("plugins/cache", text.replace("\\", "/"))
                self.assertNotIn("matched-pilot-20260717-01", text)
                self.assertIn("temp_root", text)
                self.assertIn("research/.validation-tmp", text.replace("\\", "/"))
                self.assertIn("authorized-retry-call", text)
        for relative in ("tools/validation/run_validate.ps1", "tools/validation/run_validate.sh"):
            with self.subTest(validation=relative):
                text = (REPO_ROOT / relative).read_text(encoding="utf-8").replace("\\", "/")
                for required in (
                    "teaching/pilot_runtime.py",
                    "teaching/pilot_score.py",
                    "tests/test_pilot_runtime.py",
                    "tests/test_upstream_transfer.py",
                ):
                    self.assertIn(required, text)

    def test_blocked_real_pilot_has_a_redacted_teaching_failure_case(self) -> None:
        path = REPO_ROOT / "teaching" / "pilot-failure-case-20260717.zh.md"
        self.assertTrue(path.is_file())
        text = path.read_text(encoding="utf-8")
        for required in (
            "matched-pilot-20260717-01",
            "0/18",
            "0.144.5",
            "gpt-5.6-sol",
            "9c59f899551e4d6c91d3ef3aabc057c5e2c18c85a854b131940d92ef2dde5648",
            "process-failed",
            "fail closed",
            "禁止 resume",
            "WSL 数值 arm 未执行",
        ):
            self.assertIn(required, text)
        self.assertNotIn("F:\\DeepScientistLitePilots", text)
        self.assertNotIn("G:\\DeepScientistLitePilots", text)


class PilotRuntimeBehaviorTests(unittest.TestCase):
    def execution(self) -> dict:
        return {
            "schema_version": "ds-lite.matched-pilot-execution.v1",
            "execution_id": "execution-engineering-plain-r1",
            "pilot_id": "matched-pilot-20260717-01",
            "call_id": "engineering-continuity--plain--r1",
            "case": "engineering-continuity",
            "arm": "plain",
            "round": 1,
            "status": "completed",
            "source": {
                "git_commit": "83e2e3f000000000000000000000000000000000",
                "tree_digest": "a" * 64,
                "plugin_version": "0.4.0-beta.2",
                "skill_count": 9,
                "extensions": {},
            },
            "cli": {
                "name": "codex",
                "version": "0.144.5",
                "model": "gpt-5.6-sol",
                "reasoning_effort": "low",
                "extensions": {},
            },
            "input": {
                "workspace_surface": "windows",
                "workspace_ref": "arms/engineering-continuity/plain",
                "prompt_ref": "arms/engineering-continuity/plain/TASK.md",
                "input_digest": "b" * 64,
                "extensions": {},
            },
            "usage": {
                "input_tokens": 120,
                "cached_input_tokens": 20,
                "output_tokens": 40,
                "total_tokens": 160,
                "extensions": {},
            },
            "elapsed_seconds": 12.5,
            "exit_code": 0,
            "session_id": "019f-test-session",
            "final_message": "Completed the bounded repair and tests.",
            "wsl": {
                "status": "not-required",
                "distribution": "",
                "proof_ref": "",
                "extensions": {},
            },
            "stop_reason": "completed",
            "result_refs": ["results/engineering-continuity--plain--r1.json"],
            "started_at": "2026-07-17T01:00:00Z",
            "completed_at": "2026-07-17T01:00:13Z",
            "extensions": {},
        }

    def test_execution_schema_accepts_complete_object_and_extensions(self) -> None:
        payload = self.execution()
        payload["extensions"] = {"example.org/blind-label": "group-a"}
        self.assertEqual(pilot_runtime.validate_execution(payload), payload)

    def test_current_candidate_requires_stable_codex_but_legacy_receipts_remain_readable(self) -> None:
        current = self.execution()
        current["source"]["plugin_version"] = "0.9.0-beta.1"
        current["cli"]["version"] = "0.146.0"
        self.assertEqual(pilot_runtime.validate_execution(current), current)

        current["cli"]["version"] = "0.144.5"
        with self.assertRaisesRegex(pilot_runtime.PilotError, "cli identity"):
            pilot_runtime.validate_execution(current)

        legacy = self.execution()
        self.assertEqual(pilot_runtime.validate_execution(legacy), legacy)

    def test_execution_schema_rejects_missing_field(self) -> None:
        payload = self.execution()
        payload.pop("usage")
        with self.assertRaisesRegex(pilot_runtime.PilotError, "missing fields: usage"):
            pilot_runtime.validate_execution(payload)

    def test_execution_schema_rejects_wrong_enum(self) -> None:
        payload = self.execution()
        payload["status"] = "auto-retried"
        with self.assertRaisesRegex(pilot_runtime.PilotError, "status"):
            pilot_runtime.validate_execution(payload)

    def test_execution_schema_rejects_path_escape(self) -> None:
        payload = self.execution()
        payload["input"]["prompt_ref"] = "../other-arm/TASK.md"
        with self.assertRaisesRegex(pilot_runtime.PilotError, "prompt_ref"):
            pilot_runtime.validate_execution(payload)

    def test_execution_schema_rejects_sensitive_or_hidden_reasoning_fields(self) -> None:
        payload = self.execution()
        payload["extensions"] = {"chain_of_thought": "must not persist"}
        with self.assertRaisesRegex(pilot_runtime.PilotError, "sensitive or hidden-reasoning"):
            pilot_runtime.validate_execution(payload)

    def test_execution_schema_rejects_id_conflicts(self) -> None:
        payload = self.execution()
        payload["execution_id"] = payload["call_id"]
        with self.assertRaisesRegex(pilot_runtime.PilotError, "must differ"):
            pilot_runtime.validate_execution(payload)

    def test_execution_schema_rejects_unknown_fields(self) -> None:
        payload = self.execution()
        payload["raw_jsonl"] = "events.jsonl"
        with self.assertRaisesRegex(pilot_runtime.PilotError, "unsupported fields: raw_jsonl"):
            pilot_runtime.validate_execution(payload)

    def test_execution_schema_allows_forward_compatible_extensions(self) -> None:
        payload = self.execution()
        payload["source"]["extensions"] = {"example.org/source-channel": "frozen"}
        self.assertEqual(pilot_runtime.validate_execution(payload), payload)

    def test_execution_plan_contains_fixed_eighteen_call_order(self) -> None:
        plan = pilot_runtime.build_execution_plan()
        self.assertEqual(len(plan), 18)
        observed = [(item["case"], item["arm"], item["round"]) for item in plan]
        expected = []
        for arm in ("plain", "scratchpad", "ds-lite"):
            expected.extend(("engineering-continuity", arm, round_id) for round_id in (1, 2, 3))
        expected.extend(
            [
                ("math-counterexample", "scratchpad", 1),
                ("math-counterexample", "ds-lite", 1),
                ("math-counterexample", "plain", 1),
                ("numerical-seeds", "ds-lite", 1),
                ("numerical-seeds", "plain", 1),
                ("numerical-seeds", "scratchpad", 1),
                ("idea-evaluation", "plain", 1),
                ("idea-evaluation", "ds-lite", 1),
                ("idea-evaluation", "scratchpad", 1),
            ]
        )
        self.assertEqual(observed, expected)
        self.assertTrue(all(item["codex_home"] == ("ds-lite" if item["arm"] == "ds-lite" else "control") for item in plan))
        self.assertTrue(all(item["workspace_surface"] == ("wsl" if item["case"] == "numerical-seeds" else "windows") for item in plan))

    def test_event_reducer_discards_reasoning_raw_stream_and_secrets(self) -> None:
        lines = [
            json.dumps({"type": "thread.started", "thread_id": "019f-thread"}),
            json.dumps({"type": "item.completed", "item": {"type": "reasoning", "text": "SECRET-HIDDEN"}}),
            json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": "intermediate"}}),
            json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": "public final"}}),
            json.dumps(
                {
                    "type": "turn.completed",
                    "usage": {"input_tokens": 100, "cached_input_tokens": 10, "output_tokens": 25},
                }
            ),
        ]
        reduced = pilot_runtime.reduce_event_lines(lines)
        self.assertEqual(reduced["thread_id"], "019f-thread")
        self.assertEqual(reduced["final_message"], "public final")
        self.assertEqual(reduced["usage"]["total_tokens"], 125)
        self.assertTrue(reduced["turn_completed"])
        serialized = json.dumps(reduced)
        self.assertNotIn("SECRET-HIDDEN", serialized)
        self.assertNotIn("reasoning", serialized)
        self.assertNotIn("intermediate", serialized)

    def test_event_reducer_redacts_structured_errors_and_collaboration_prompts(self) -> None:
        secret = "FAKE-STRUCTURED-ERROR-SECRET"
        lines = [
            json.dumps({"type": "thread.started", "thread_id": "019f-parent"}),
            json.dumps(
                {
                    "type": "item.completed",
                    "item": {
                        "type": "collab_tool_call",
                        "tool": "spawn_agent",
                        "receiver_thread_ids": ["019f-child-a", "019f-child-b"],
                        "prompt": f"do not persist {secret}",
                        "status": "completed",
                    },
                }
            ),
            json.dumps(
                {
                    "type": "turn.failed",
                    "error": {"message": f"HTTP 401 code=invalid_api_key {secret}"},
                }
            ),
            json.dumps({"type": "error", "message": f"transport disconnected {secret}"}),
        ]

        reduced = pilot_runtime.reduce_event_lines(lines)

        self.assertTrue(reduced["turn_failed"])
        self.assertEqual(reduced["tool_count"], 1)
        self.assertEqual(reduced["collaboration_summary"]["spawn_count"], 1)
        self.assertEqual(reduced["collaboration_summary"]["receiver_count"], 2)
        self.assertEqual(len(reduced["collaboration_summary"]["receiver_id_sha256"]), 2)
        self.assertEqual(reduced["structured_error_summary"]["count"], 2)
        self.assertEqual(
            reduced["structured_error_summary"]["sources"],
            ["error", "turn.failed"],
        )
        serialized = json.dumps(reduced, ensure_ascii=False)
        self.assertNotIn(secret, serialized)
        self.assertNotIn("invalid_api_key", serialized)
        self.assertNotIn("do not persist", serialized)

    def test_progress_context_uses_fixed_call_order_and_relative_receipt(self) -> None:
        self.assertTrue(hasattr(pilot_runtime, "build_progress_context"))
        item = pilot_runtime.build_execution_plan()[6]
        context = pilot_runtime.build_progress_context(item, call_number=7, total_calls=18)
        self.assertEqual(
            context,
            {
                "call_number": 7,
                "total_calls": 18,
                "receipt_ref": item["result_ref"],
            },
        )
        rendered = json.dumps(context)
        self.assertNotIn("workspace_ref", rendered)
        self.assertNotIn("codex_home", rendered)

    def test_progress_projection_uses_fake_clock_for_sixty_second_heartbeat(self) -> None:
        for method in ("start", "observe", "heartbeat", "finish"):
            self.assertTrue(hasattr(pilot_runtime.PilotProgress, method), method)

        now = [100.0]
        snapshots: list[dict] = []
        progress = pilot_runtime.PilotProgress(
            call_number=7,
            total_calls=18,
            case="numerical-seeds",
            arm="ds-lite",
            round_number=1,
            receipt_ref="results/executions/numerical-ds-lite.json",
            timeout_seconds=180,
            clock=lambda: now[0],
            sink=snapshots.append,
        )
        progress.start()
        self.assertEqual(len(snapshots), 1)
        now[0] = 159.0
        self.assertFalse(progress.heartbeat())
        self.assertEqual(len(snapshots), 1)
        now[0] = 160.0
        self.assertTrue(progress.heartbeat())
        heartbeat = snapshots[-1]
        self.assertEqual(heartbeat["call"], "7/18")
        self.assertEqual(heartbeat["last_event_age_seconds"], 60.0)
        self.assertEqual(heartbeat["elapsed_seconds"], 60.0)
        self.assertEqual(heartbeat["remaining_seconds"], 120.0)
        self.assertFalse(heartbeat["thread_established"])

        progress.observe("tool", thread_established=True, tool_count=2)
        observed = snapshots[-1]
        self.assertEqual(observed["event_category"], "tool")
        self.assertTrue(observed["thread_established"])
        self.assertEqual(observed["tool_count"], 2)
        self.assertEqual(observed["last_event_age_seconds"], 0.0)

        progress.finish("failed", "transport")
        self.assertEqual(snapshots[-1]["status"], "failed")
        self.assertEqual(snapshots[-1]["failure_category"], "transport")

    def test_silent_process_failure_still_emits_actionable_redacted_progress(self) -> None:
        signature = inspect.signature(pilot_runtime.run_codex_call)
        self.assertIn("progress_context", signature.parameters)
        self.assertIn("progress_sink", signature.parameters)

        root = Path(tempfile.mkdtemp(prefix="ds-lite-silent-codex-"))
        fake = root / "silent_codex.py"
        fake.write_text("raise SystemExit(7)\n", encoding="utf-8")
        payload = self.execution()
        payload.update(
            {
                "execution_id": "execution-silent",
                "call_id": "call-silent",
                "status": "pending",
                "elapsed_seconds": 0,
                "exit_code": None,
                "session_id": "",
                "final_message": "",
                "stop_reason": "not-started",
                "completed_at": "",
            }
        )
        snapshots: list[dict] = []
        secret_prompt = "perform one bounded task token=never-echo-this"
        result = pilot_runtime.run_codex_call(
            codex_bin=fake,
            cwd=root,
            codex_home=root / "home",
            prompt=secret_prompt,
            record_path=root / "silent.json",
            execution=payload,
            timeout_seconds=5,
            progress_context={
                "call_number": 1,
                "total_calls": 18,
                "receipt_ref": "results/executions/silent.json",
            },
            progress_sink=snapshots.append,
        )
        self.assertEqual(result["status"], "failed")
        self.assertGreaterEqual(len(snapshots), 2)
        final = snapshots[-1]
        self.assertEqual(final["status"], "failed")
        self.assertEqual(final["failure_category"], "process")
        self.assertFalse(final["thread_established"])
        self.assertEqual(final["tool_count"], 0)
        self.assertEqual(final["receipt_ref"], "results/executions/silent.json")
        rendered = json.dumps(snapshots, ensure_ascii=False)
        self.assertNotIn("never-echo-this", rendered)
        self.assertNotIn(str(root), rendered)

    def test_spawn_failure_terminalizes_receipt_with_redacted_diagnostic(self) -> None:
        root = Path(tempfile.mkdtemp(prefix="ds-lite-spawn-failure-"))
        payload = self.execution()
        payload.update(
            {
                "execution_id": "execution-spawn-failure",
                "call_id": "call-spawn-failure",
                "status": "pending",
                "elapsed_seconds": 0,
                "exit_code": None,
                "session_id": "",
                "final_message": "",
                "stop_reason": "not-started",
                "completed_at": "",
            }
        )
        record_path = root / "spawn-failure.json"
        result = pilot_runtime.run_codex_call(
            codex_bin=root / "missing-codex.exe",
            cwd=root,
            codex_home=root / "home",
            prompt="perform one bounded fake task",
            record_path=record_path,
            execution=payload,
            timeout_seconds=5,
        )

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["stop_reason"], "process-failed")
        diagnostic = result["extensions"]["process_diagnostic"]
        self.assertEqual(diagnostic["failure_class"], "child-process")
        self.assertEqual(diagnostic["subprocess_exit_cause"], "spawn-error")
        self.assertEqual(json.loads(record_path.read_text(encoding="utf-8"))["status"], "failed")

    def test_resume_skips_only_completed_and_blocks_uncertain_or_failed_calls(self) -> None:
        decision = pilot_runtime.resume_decision(
            [
                {"call_id": "call-1", "status": "completed", "stop_reason": "completed"},
                {"call_id": "call-2", "status": "pending", "stop_reason": "not-started"},
            ]
        )
        self.assertEqual(decision["action"], "continue")
        self.assertEqual(decision["skip_completed"], ["call-1"])
        for status, reason in (
            ("running", "operator-stop"),
            ("ambiguous", "ambiguous-transport"),
            ("timeout", "timeout"),
            ("blocked", "duplicate-risk"),
            ("failed", "process-failed"),
        ):
            with self.subTest(status=status, reason=reason):
                blocked = pilot_runtime.resume_decision(
                    [{"call_id": "call-risk", "status": status, "stop_reason": reason}]
                )
                self.assertEqual(blocked["action"], "stop")
                self.assertIn("call-risk", blocked["blocking_calls"])

    def test_attempt_retry_requires_transient_failure_and_absent_workspace_effect(self) -> None:
        before = {"TASK.md": "a" * 64}
        transient = {
            "status": "failed",
            "stop_reason": "process-failed",
            "extensions": {
                "process_diagnostic": {
                    "failure_class": "network",
                    "http_status_category": "none",
                }
            },
        }
        decision = pilot_runtime.reconcile_attempt_retry(
            transient,
            before_inventory=before,
            after_inventory=dict(before),
            attempt_number=1,
            max_attempts=3,
        )
        self.assertEqual(decision["disposition"], "retry")
        self.assertTrue(decision["effect_absent"])
        self.assertGreater(decision["delay_seconds"], 0)

        changed = pilot_runtime.reconcile_attempt_retry(
            transient,
            before_inventory=before,
            after_inventory={**before, "REPORT.md": "b" * 64},
            attempt_number=1,
            max_attempts=3,
        )
        self.assertEqual(changed["disposition"], "blocked")
        self.assertEqual(changed["reason"], "workspace-effect-observed")

    def test_attempt_retry_fails_closed_for_auth_ambiguous_and_exhaustion(self) -> None:
        inventory = {"TASK.md": "a" * 64}
        for result, expected_reason in (
            (
                {
                    "status": "failed",
                    "stop_reason": "process-failed",
                    "extensions": {"process_diagnostic": {"failure_class": "auth", "http_status_category": "4xx"}},
                },
                "non-retryable-failure",
            ),
            (
                {
                    "status": "ambiguous",
                    "stop_reason": "ambiguous-transport",
                    "extensions": {"process_diagnostic": {"failure_class": "ambiguous", "http_status_category": "none"}},
                },
                "ambiguous-effect",
            ),
        ):
            with self.subTest(expected_reason=expected_reason):
                decision = pilot_runtime.reconcile_attempt_retry(
                    result,
                    before_inventory=inventory,
                    after_inventory=dict(inventory),
                    attempt_number=1,
                    max_attempts=3,
                )
                self.assertEqual(decision["disposition"], "blocked")
                self.assertEqual(decision["reason"], expected_reason)

        exhausted = pilot_runtime.reconcile_attempt_retry(
            {
                "status": "timeout",
                "stop_reason": "timeout",
                "extensions": {"process_diagnostic": {"failure_class": "timeout", "http_status_category": "none"}},
            },
            before_inventory=inventory,
            after_inventory=dict(inventory),
            attempt_number=3,
            max_attempts=3,
        )
        self.assertEqual(exhausted["reason"], "attempt-budget-exhausted")

    def test_terminal_attempts_are_write_once_and_only_success_becomes_canonical(self) -> None:
        root = Path(tempfile.mkdtemp(prefix="ds-lite-pilot-attempts-"))
        item = {
            "call_id": "math-counterexample--plain--r1",
            "result_ref": "results/executions/math-counterexample--plain--r1.json",
        }
        failed = self.execution()
        failed.update(
            {
                "execution_id": "execution:math-counterexample--plain--r1:attempt:1",
                "call_id": item["call_id"],
                "status": "failed",
                "exit_code": 1,
                "stop_reason": "process-failed",
                "completed_at": "2026-08-01T00:00:00Z",
            }
        )
        failed_ref = pilot_runtime.persist_terminal_attempt(root, item, failed, attempt_number=1)
        self.assertTrue((root / failed_ref["attempt_ref"]).is_file())
        self.assertFalse((root / item["result_ref"]).exists())
        with self.assertRaises(FileExistsError):
            pilot_runtime.persist_terminal_attempt(root, item, failed, attempt_number=1)

        completed = self.execution()
        completed.update(
            {
                "execution_id": "execution:math-counterexample--plain--r1:attempt:2",
                "call_id": item["call_id"],
            }
        )
        success_ref = pilot_runtime.persist_terminal_attempt(root, item, completed, attempt_number=2)
        canonical = root / item["result_ref"]
        index = root / success_ref["index_ref"]
        self.assertEqual(canonical.read_bytes(), (root / success_ref["attempt_ref"]).read_bytes())
        self.assertEqual(json.loads(index.read_text(encoding="utf-8"))["canonical_attempt_number"], 2)
        self.assertEqual(json.loads(index.read_text(encoding="utf-8"))["canonical_sha256"], success_ref["attempt_sha256"])

    def test_call_attempt_sequence_retries_transient_absent_effect_and_indexes_success(self) -> None:
        root = Path(tempfile.mkdtemp(prefix="ds-lite-pilot-sequence-"))
        workspace = root / "arms" / "math-counterexample" / "plain"
        workspace.mkdir(parents=True)
        (workspace / "TASK.md").write_text("bounded task\n", encoding="utf-8")
        item = {
            "call_id": "math-counterexample--plain--r1",
            "result_ref": "results/executions/math-counterexample--plain--r1.json",
        }
        base = self.execution()
        base.update({"call_id": item["call_id"], "case": "math-counterexample"})
        calls = []

        def invoke(attempt_number: int, execution: dict, runtime_path: Path) -> dict:
            calls.append((attempt_number, runtime_path))
            if attempt_number == 2:
                (workspace / "REPORT.md").write_text("completed effect\n", encoding="utf-8")
            result = dict(execution)
            result.update(
                {
                    "status": "failed" if attempt_number == 1 else "completed",
                    "exit_code": 1 if attempt_number == 1 else 0,
                    "stop_reason": "process-failed" if attempt_number == 1 else "completed",
                    "completed_at": f"2026-08-01T00:00:0{attempt_number}Z",
                }
            )
            result["extensions"] = {
                "process_diagnostic": {
                    "failure_class": "network" if attempt_number == 1 else "none",
                    "http_status_category": "none",
                }
            }
            return result

        delays = []
        result = pilot_runtime.run_call_attempt_sequence(
            root,
            workspace=workspace,
            item=item,
            base_execution=base,
            invoke=invoke,
            max_attempts=3,
            sleep_fn=delays.append,
        )
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["extensions"]["attempt_reconciliation"]["disposition"], "terminal")
        self.assertEqual(result["extensions"]["attempt_reconciliation"]["reason"], "completed")
        self.assertEqual([number for number, _ in calls], [1, 2])
        self.assertEqual(delays, [5])
        self.assertTrue((root / "results/execution-attempts/math-counterexample--plain--r1/attempt-001.json").is_file())
        self.assertTrue((root / "results/execution-attempts/math-counterexample--plain--r1/attempt-002.json").is_file())
        self.assertEqual(
            json.loads((root / "results/execution-index/math-counterexample--plain--r1.json").read_text(encoding="utf-8"))["canonical_attempt_number"],
            2,
        )

    def test_call_attempt_sequence_does_not_retry_after_workspace_effect(self) -> None:
        root = Path(tempfile.mkdtemp(prefix="ds-lite-pilot-effect-"))
        workspace = root / "workspace"
        workspace.mkdir()
        (workspace / "TASK.md").write_text("bounded task\n", encoding="utf-8")
        item = {"call_id": "call-effect", "result_ref": "results/executions/call-effect.json"}
        base = self.execution()
        base.update({"execution_id": "execution-call-effect", "call_id": "call-effect"})
        call_count = 0

        def invoke(attempt_number: int, execution: dict, runtime_path: Path) -> dict:
            nonlocal call_count
            call_count += 1
            (workspace / "REPORT.md").write_text("partial effect\n", encoding="utf-8")
            result = dict(execution)
            result.update({"status": "failed", "exit_code": 1, "stop_reason": "process-failed", "completed_at": "2026-08-01T00:00:01Z"})
            result["extensions"] = {"process_diagnostic": {"failure_class": "network", "http_status_category": "none"}}
            return result

        result = pilot_runtime.run_call_attempt_sequence(
            root,
            workspace=workspace,
            item=item,
            base_execution=base,
            invoke=invoke,
            max_attempts=3,
            sleep_fn=lambda _seconds: self.fail("workspace effects must prevent retry"),
        )
        self.assertEqual(result["status"], "failed")
        self.assertEqual(call_count, 1)
        self.assertEqual(result["extensions"]["attempt_reconciliation"]["reason"], "workspace-effect-observed")
        self.assertFalse((root / item["result_ref"]).exists())

    def test_one_operator_authorized_retry_can_recover_exact_terminal_auth_attempt(self) -> None:
        root = Path(tempfile.mkdtemp(prefix="ds-lite-pilot-operator-retry-"))
        workspace = root / "workspace"
        workspace.mkdir()
        (workspace / "TASK.md").write_text("bounded task\n", encoding="utf-8")
        item = {"call_id": "call-auth", "result_ref": "results/executions/call-auth.json"}
        prior = self.execution()
        prior.update(
            {
                "execution_id": "execution:call-auth:attempt:1",
                "call_id": "call-auth",
                "status": "failed",
                "exit_code": 1,
                "stop_reason": "process-failed",
                "completed_at": "2026-08-01T00:00:01Z",
            }
        )
        inventory = pilot_runtime._inventory(workspace)
        prior["extensions"] = {
            "event_summary": {"turn_failed": True},
            "process_diagnostic": {"failure_class": "auth", "http_status_category": "4xx"},
            "attempt_reconciliation": pilot_runtime.reconcile_attempt_retry(
                prior,
                before_inventory=inventory,
                after_inventory=dict(inventory),
                attempt_number=1,
                max_attempts=3,
            ),
        }
        pilot_runtime.persist_terminal_attempt(root, item, prior, attempt_number=1)
        calls = []

        def invoke(attempt_number: int, execution: dict, runtime_path: Path) -> dict:
            calls.append(attempt_number)
            result = dict(execution)
            result.update({"status": "completed", "exit_code": 0, "stop_reason": "completed", "completed_at": "2026-08-01T00:00:02Z"})
            result["extensions"] = {"process_diagnostic": {"failure_class": "none", "http_status_category": "none"}}
            return result

        result = pilot_runtime.run_call_attempt_sequence(
            root,
            workspace=workspace,
            item=item,
            base_execution={**prior, "status": "pending", "exit_code": None, "stop_reason": "not-started", "completed_at": "", "extensions": {}},
            invoke=invoke,
            max_attempts=3,
            authorized_retry=True,
            authorization_ref="phase5-user-authorization-20260801",
            sleep_fn=lambda _seconds: None,
        )
        self.assertEqual(result["status"], "completed")
        self.assertEqual(calls, [2])
        authorization = result["extensions"]["operator_retry_authorization"]
        self.assertEqual(authorization["prior_attempt_number"], 1)
        self.assertRegex(authorization["prior_attempt_sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(authorization["authorization_ref"], "phase5-user-authorization-20260801")

    def test_operator_retry_can_recover_exact_effect_absent_wsl_precondition(self) -> None:
        root = Path(tempfile.mkdtemp(prefix="ds-lite-pilot-wsl-retry-"))
        workspace = root / "workspace"
        workspace.mkdir()
        (workspace / "TASK.md").write_text("bounded task\n", encoding="utf-8")
        item = {"call_id": "numerical-seeds--plain--r1", "result_ref": "results/executions/numerical-seeds--plain--r1.json"}
        prior = self.execution()
        prior.update(
            {
                "execution_id": "execution:numerical-seeds--plain--r1:attempt:1",
                "call_id": item["call_id"],
                "case": "numerical-seeds",
                "status": "blocked",
                "stop_reason": "precondition",
                "input": {**prior["input"], "workspace_surface": "wsl"},
                "wsl": {"status": "missing", "distribution": "DS-Lite-Ubuntu-24.04", "proof_ref": "", "extensions": {}},
            }
        )
        inventory = pilot_runtime._inventory(workspace)
        prior["extensions"] = {
            "event_summary": {"turn_completed": True, "turn_failed": False},
            "process_diagnostic": {"failure_class": "none", "http_status_category": "none"},
            "attempt_reconciliation": pilot_runtime.reconcile_attempt_retry(
                prior,
                before_inventory=inventory,
                after_inventory=dict(inventory),
                attempt_number=1,
                max_attempts=3,
            ),
        }
        pilot_runtime.persist_terminal_attempt(root, item, prior, attempt_number=1)
        calls = []

        def invoke(attempt_number: int, execution: dict, runtime_path: Path) -> dict:
            calls.append(attempt_number)
            return prior

        pilot_runtime.run_call_attempt_sequence(
            root,
            workspace=workspace,
            item=item,
            base_execution=prior,
            invoke=invoke,
            max_attempts=3,
            authorized_retry=True,
            authorization_ref="phase5-user-authorization-20260801",
        )
        self.assertEqual(calls, [2])

    def test_prepare_and_install_create_cross_drive_isolated_homes(self) -> None:
        parent = Path(tempfile.mkdtemp(prefix="ds-lite-pilot-layout-"))
        windows_root = parent / "windows" / "pilot"
        wsl_root = parent / "wsl" / "pilot"
        pilot_runtime.prepare_pilot(
            windows_root,
            wsl_root,
            repo_root=REPO_ROOT,
            pilot_id="matched-pilot-test",
            authorization_ref="user-approved-test",
        )
        self.assertTrue((windows_root / "pilot-manifest.json").is_file())
        self.assertTrue((windows_root / "execution-plan.json").is_file())
        self.assertTrue((windows_root / "source-snapshot" / "plugins" / "deepscientist-lite-core" / "skills").is_dir())
        self.assertTrue((wsl_root / "arms" / "numerical-seeds" / "plain" / "TASK.md").is_file())
        wrapper = wsl_root / "arms" / "numerical-seeds" / "plain" / "materials" / "run_simulation_wsl.sh"
        self.assertTrue(wrapper.is_file())
        wrapper_text = wrapper.read_text(encoding="utf-8")
        self.assertIn("WSL_DISTRO_NAME", wrapper_text)
        self.assertIn("wsl-proof", wrapper_text)
        self.assertNotIn(str(wsl_root), wrapper_text)
        plan_text = (windows_root / "execution-plan.json").read_text(encoding="utf-8")
        self.assertNotIn(str(windows_root), plan_text)
        self.assertNotIn(str(wsl_root), plan_text)

        pilot_runtime.install_homes(windows_root)
        control_skills = windows_root / "homes" / "control" / "skills"
        ds_lite_skills = windows_root / "homes" / "ds-lite" / "skills"
        self.assertEqual(list(control_skills.iterdir()), [])
        discovered = [
            path
            for path in ds_lite_skills.iterdir()
            if path.is_dir() and (path / "SKILL.md").is_file()
        ]
        self.assertEqual(len(discovered), 9)
        home_manifest = (windows_root / "home-manifest.json").read_text(encoding="utf-8")
        self.assertNotIn(str(windows_root), home_manifest)
        self.assertIn('"installation_kind": "isolated-skill-home"', home_manifest)
        self.assertIn('"cache_installation_verified": false', home_manifest)

        manifest_text = (windows_root / "pilot-manifest.json").read_text(encoding="utf-8")
        self.assertIn('"actual_execution_authorization": "user-approved-test"', manifest_text)
        self.assertNotIn("granted-2026-07-17", manifest_text)

    def test_install_clones_nonsecret_provider_route_and_model_catalog(self) -> None:
        parent = Path(tempfile.mkdtemp(prefix="ds-lite-pilot-provider-config-"))
        windows_root = parent / "windows"
        wsl_root = parent / "wsl"
        formal_home = parent / "formal-home"
        (formal_home / "model-catalogs").mkdir(parents=True)
        (formal_home / "model-catalogs" / "catalog.json").write_text(
            '{"models":[{"slug":"gpt-5.6-sol"}]}\n', encoding="utf-8"
        )
        (formal_home / "auth.json").write_text('{"token":"must-not-copy"}\n', encoding="utf-8")
        (formal_home / "config.toml").write_text(
            'model_provider = "custom"\n'
            'model = "gpt-5.6-sol"\n'
            'model_reasoning_effort = "medium"\n'
            'model_catalog_json = "model-catalogs/catalog.json"\n\n'
            '[model_providers.custom]\n'
            'name = "custom"\n'
            'base_url = "https://provider.example/v1"\n'
            'wire_api = "responses"\n'
            'requires_openai_auth = true\n'
            'request_max_retries = 9\n'
            'stream_max_retries = 7\n',
            encoding="utf-8",
        )
        pilot_runtime.prepare_pilot(
            windows_root,
            wsl_root,
            repo_root=REPO_ROOT,
            pilot_id="matched-pilot-provider-config",
            authorization_ref="user-approved-provider-config",
        )
        pilot_runtime.install_homes(windows_root, source_codex_home=formal_home)
        isolated = (windows_root / "homes" / "ds-lite" / "config.toml").read_text(encoding="utf-8")
        self.assertIn('model_provider = "custom"', isolated)
        self.assertIn('base_url = "https://provider.example/v1"', isolated)
        self.assertIn('wire_api = "responses"', isolated)
        self.assertIn("requires_openai_auth = true", isolated)
        self.assertIn('env_key = "OPENAI_API_KEY"', isolated)
        self.assertIn('model_catalog_json = "model-catalogs/catalog.json"', isolated)
        self.assertIn("request_max_retries = 0", isolated)
        self.assertIn("stream_max_retries = 0", isolated)
        self.assertNotIn("request_max_retries = 9", isolated)
        self.assertNotIn("stream_max_retries = 7", isolated)
        self.assertTrue((windows_root / "homes" / "ds-lite" / "model-catalogs" / "catalog.json").is_file())
        self.assertFalse((windows_root / "homes" / "ds-lite" / "auth.json").exists())
        home_manifest = json.loads((windows_root / "home-manifest.json").read_text(encoding="utf-8"))
        route = home_manifest["extensions"]["provider_config"]["ds_lite"]["route_fidelity"]
        self.assertTrue(route["required_fields_match"])
        self.assertTrue(route["auth_env_key_configured"])
        self.assertEqual(
            route["copied_fields_present"],
            ["base_url", "name", "requires_openai_auth", "wire_api"],
        )
        self.assertEqual(route["request_max_retries"], 0)
        self.assertEqual(route["stream_max_retries"], 0)
        self.assertNotIn("provider.example", json.dumps(route))

    def test_prepare_requires_current_authorization_and_refuses_frozen_pilot_id(self) -> None:
        parent = Path(tempfile.mkdtemp(prefix="ds-lite-pilot-authorization-"))
        with self.assertRaisesRegex(TypeError, "authorization_ref"):
            pilot_runtime.prepare_pilot(
                parent / "missing-auth-windows",
                parent / "missing-auth-wsl",
                repo_root=REPO_ROOT,
                pilot_id="matched-pilot-current",
            )
        with self.assertRaisesRegex(pilot_runtime.PilotError, "frozen pilot"):
            pilot_runtime.prepare_pilot(
                parent / "old-windows",
                parent / "old-wsl",
                repo_root=REPO_ROOT,
                pilot_id="matched-pilot-20260717-01",
                authorization_ref="user-approved-test",
            )

    def _write_fake_host(self, root: Path) -> tuple[Path, Path]:
        fake_codex = root / "fake_codex.py"
        fake_codex.write_text(
            textwrap.dedent(
                """
                import json
                import os
                from pathlib import Path
                import sys

                args = sys.argv[1:]
                if args == ["--version"]:
                    print("codex-cli 0.146.0")
                elif args[:2] == ["login", "status"]:
                    if os.environ.get("FAKE_LOGIN_STATUS") == "not-logged-in":
                        print("Not logged in")
                        raise SystemExit(1)
                    print("Logged in using an API key - sk-never-persist-this")
                elif args[:2] == ["features", "list"]:
                    print("hooks stable true")
                    print("plugins stable true")
                    print("multi_agent stable true")
                    print("plugin_hooks removed false")
                elif args[:2] == ["debug", "prompt-input"]:
                    home = Path(os.environ["CODEX_HOME"])
                    skills = sorted(path.name for path in (home / "skills").iterdir())
                    print(json.dumps({"skills": skills, "home": str(home), "token": "sk-never-persist-this"}))
                elif "exec" in args:
                    print(json.dumps({"type": "thread.started", "thread_id": "019f-canary"}), flush=True)
                    print(json.dumps({"type": "item.completed", "item": {"type": "command_execution"}}), flush=True)
                    print(json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": "DS Lite selected ds-lite for a bounded status check."}}), flush=True)
                    zero = os.environ.get("FAKE_ZERO_USAGE") == "1"
                    usage = {"input_tokens": 0, "output_tokens": 0} if zero else {"input_tokens": 9, "output_tokens": 3}
                    print(json.dumps({"type": "turn.completed", "usage": usage}), flush=True)
                else:
                    raise SystemExit(2)
                """
            ).strip()
            + "\n",
            encoding="utf-8",
        )
        fake_wsl = root / "fake_wsl.py"
        fake_wsl.write_text("print('wsl: non-fatal warning')\nprint('Linux')\n", encoding="utf-8")
        return fake_codex, fake_wsl

    def _write_provider_home(self, root: Path) -> Path:
        provider_home = root / "provider-home"
        provider_home.mkdir()
        (provider_home / "config.toml").write_text(
            'model_provider = "custom"\n\n'
            '[model_providers.custom]\n'
            'name = "custom"\n'
            'base_url = "https://provider.example/v1"\n'
            'wire_api = "responses"\n'
            'requires_openai_auth = true\n',
            encoding="utf-8",
        )
        return provider_home

    def test_preflight_proves_isolated_prompt_skills_without_persisting_host_output(self) -> None:
        parent = Path(tempfile.mkdtemp(prefix="ds-lite-preflight-"))
        windows_root = parent / "windows"
        wsl_root = parent / "wsl"
        pilot_runtime.prepare_pilot(
            windows_root,
            wsl_root,
            repo_root=REPO_ROOT,
            pilot_id="matched-pilot-preflight",
            authorization_ref="user-approved-preflight",
        )
        pilot_runtime.install_homes(
            windows_root,
            source_codex_home=self._write_provider_home(parent),
        )
        fake_codex, fake_wsl = self._write_fake_host(parent)

        result = pilot_runtime.preflight_pilot(
            windows_root,
            wsl_root,
            codex_bin=fake_codex,
            wsl_bin=fake_wsl,
        )
        self.assertEqual(result["status"], "passed")
        self.assertTrue(result["cli"]["authenticated"])
        self.assertEqual(result["homes"]["control"]["prompt_skill_names"], [])
        self.assertEqual(len(result["homes"]["ds_lite"]["prompt_skill_names"]), 9)
        self.assertFalse(result["extensions"]["cache_installation_verified"])
        saved = (windows_root / "results" / "preflight.json").read_text(encoding="utf-8")
        self.assertNotIn(str(parent), saved)
        self.assertNotIn("sk-never-persist-this", saved)
        self.assertNotIn("Logged in using", saved)

    def test_preflight_accepts_environment_api_key_category_without_persisting_value(self) -> None:
        parent = Path(tempfile.mkdtemp(prefix="ds-lite-preflight-env-auth-"))
        windows_root = parent / "windows"
        wsl_root = parent / "wsl"
        pilot_runtime.prepare_pilot(
            windows_root,
            wsl_root,
            repo_root=REPO_ROOT,
            pilot_id="matched-pilot-preflight-env-auth",
            authorization_ref="user-approved-preflight-env-auth",
        )
        pilot_runtime.install_homes(
            windows_root,
            source_codex_home=self._write_provider_home(parent),
        )
        fake_codex, fake_wsl = self._write_fake_host(parent)
        original_key = os.environ.get("OPENAI_API_KEY")
        original_status = os.environ.get("FAKE_LOGIN_STATUS")
        os.environ["OPENAI_API_KEY"] = "sk-environment-value-must-not-persist"
        os.environ["FAKE_LOGIN_STATUS"] = "not-logged-in"
        try:
            result = pilot_runtime.preflight_pilot(
                windows_root,
                wsl_root,
                codex_bin=fake_codex,
                wsl_bin=fake_wsl,
            )
        finally:
            if original_key is None:
                os.environ.pop("OPENAI_API_KEY", None)
            else:
                os.environ["OPENAI_API_KEY"] = original_key
            if original_status is None:
                os.environ.pop("FAKE_LOGIN_STATUS", None)
            else:
                os.environ["FAKE_LOGIN_STATUS"] = original_status
        self.assertEqual(result["status"], "passed")
        self.assertTrue(result["cli"]["authenticated"])
        self.assertEqual(result["cli"]["authentication_source"], "environment-api-key")
        saved = (windows_root / "results" / "preflight.json").read_text(encoding="utf-8")
        self.assertNotIn("sk-environment-value-must-not-persist", saved)

    def test_canary_requires_implicit_skill_evidence_nonzero_usage_and_no_workspace_change(self) -> None:
        parent = Path(tempfile.mkdtemp(prefix="ds-lite-canary-"))
        windows_root = parent / "windows"
        wsl_root = parent / "wsl"
        pilot_runtime.prepare_pilot(
            windows_root,
            wsl_root,
            repo_root=REPO_ROOT,
            pilot_id="matched-pilot-canary",
            authorization_ref="user-approved-canary",
        )
        pilot_runtime.install_homes(
            windows_root,
            source_codex_home=self._write_provider_home(parent),
        )
        fake_codex, fake_wsl = self._write_fake_host(parent)
        pilot_runtime.preflight_pilot(
            windows_root,
            wsl_root,
            codex_bin=fake_codex,
            wsl_bin=fake_wsl,
        )
        prompt = (windows_root / "canary" / "PROMPT.md").read_text(encoding="utf-8")
        self.assertNotIn("$ds-lite", prompt)

        result = pilot_runtime.run_canary(windows_root, codex_bin=fake_codex, timeout_seconds=5)
        self.assertEqual(result["status"], "completed")
        self.assertTrue(result["extensions"]["canary"]["passed"])
        self.assertEqual(result["extensions"]["canary"]["observed_skill"], "ds-lite")
        self.assertTrue(result["extensions"]["canary"]["workspace_unchanged"])
        saved = (windows_root / "results" / "canary.json").read_text(encoding="utf-8")
        self.assertNotIn(str(parent), saved)
        self.assertNotIn("PROMPT.md", result["final_message"])

    def test_canary_blocks_completed_turn_with_zero_usage(self) -> None:
        parent = Path(tempfile.mkdtemp(prefix="ds-lite-canary-zero-"))
        windows_root = parent / "windows"
        wsl_root = parent / "wsl"
        pilot_runtime.prepare_pilot(
            windows_root,
            wsl_root,
            repo_root=REPO_ROOT,
            pilot_id="matched-pilot-canary-zero",
            authorization_ref="user-approved-canary-zero",
        )
        pilot_runtime.install_homes(
            windows_root,
            source_codex_home=self._write_provider_home(parent),
        )
        fake_codex, fake_wsl = self._write_fake_host(parent)
        pilot_runtime.preflight_pilot(
            windows_root,
            wsl_root,
            codex_bin=fake_codex,
            wsl_bin=fake_wsl,
        )
        original = os.environ.get("FAKE_ZERO_USAGE")
        os.environ["FAKE_ZERO_USAGE"] = "1"
        try:
            result = pilot_runtime.run_canary(windows_root, codex_bin=fake_codex, timeout_seconds=5)
        finally:
            if original is None:
                os.environ.pop("FAKE_ZERO_USAGE", None)
            else:
                os.environ["FAKE_ZERO_USAGE"] = original
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["stop_reason"], "precondition")
        self.assertIn("nonzero-usage", result["extensions"]["canary"]["blocking_reasons"])

    def test_canary_receipt_contains_a_terminal_acceptance_gate(self) -> None:
        parent = Path(tempfile.mkdtemp(prefix="ds-lite-canary-gate-"))
        windows_root = parent / "windows"
        wsl_root = parent / "wsl"
        pilot_runtime.prepare_pilot(
            windows_root,
            wsl_root,
            repo_root=REPO_ROOT,
            pilot_id="matched-pilot-gate",
            authorization_ref="user-approved-gate",
        )
        pilot_runtime.install_homes(windows_root)
        (windows_root / "results" / "preflight.json").write_text(
            json.dumps({"status": "passed"}), encoding="utf-8"
        )
        fake_codex = parent / "fake-gate-codex.py"
        fake_codex.write_text(
            "import json, sys\n"
            "if '--version' in sys.argv:\n"
            "    print('codex 0.146.0')\n"
            "    raise SystemExit(0)\n"
            "print(json.dumps({'type':'thread.started','thread_id':'019f-gate'}), flush=True)\n"
            "print(json.dumps({'type':'item.completed','item':{'type':'command_execution','command':'pwd','exit_code':0}}), flush=True)\n"
            "print(json.dumps({'type':'item.completed','item':{'type':'agent_message','text':'ds-lite checked the project and stopped.'}}), flush=True)\n"
            "print(json.dumps({'type':'turn.completed','usage':{'input_tokens':2,'output_tokens':3,'total_tokens':5}}), flush=True)\n",
            encoding="utf-8",
        )
        result = pilot_runtime.run_canary(windows_root, codex_bin=fake_codex, timeout_seconds=5)
        gate = result["extensions"]["acceptance_gate"]
        self.assertEqual(gate["status"], "passed")
        self.assertTrue(pilot_runtime.acceptance_gate.can_enter_next_gate(gate))

    def test_execution_loop_numbers_calls_before_building_progress_context(self) -> None:
        source = inspect.getsource(pilot_runtime.execute_pilot)
        self.assertIn("for call_number, item in enumerate(plan, start=1):", source)

    def test_execution_loop_routes_each_logical_call_through_attempt_recovery(self) -> None:
        source = inspect.getsource(pilot_runtime.execute_pilot)
        self.assertIn("run_call_attempt_sequence(", source)
        self.assertNotIn("record_path=record_path", source)

    def test_resume_cli_accepts_an_exact_operator_authorized_retry_call(self) -> None:
        args = pilot_runtime.parser().parse_args(
            [
                "resume",
                "--windows-root", "windows",
                "--wsl-root", "wsl",
                "--codex-bin", "codex.exe",
                "--authorized-retry-call", "engineering-continuity--scratchpad--r3",
                "--authorization-ref", "phase5-user-authorization-20260801",
            ]
        )
        self.assertEqual(args.authorized_retry_call, ["engineering-continuity--scratchpad--r3"])
        self.assertEqual(args.authorization_ref, "phase5-user-authorization-20260801")

    def test_fake_codex_records_success_failure_and_ambiguous_without_raw_jsonl(self) -> None:
        root = Path(tempfile.mkdtemp(prefix="ds-lite-fake-codex-"))
        fake = root / "fake_codex.py"
        fake.write_text(
            textwrap.dedent(
                """
                import json
                import os
                import sys
                import time

                mode = os.environ.get("FAKE_CODEX_MODE", "success")
                print(json.dumps({"type": "thread.started", "thread_id": "019f-fake"}), flush=True)
                print(json.dumps({"type": "item.completed", "item": {"type": "reasoning", "text": "FAKE-SECRET"}}), flush=True)
                print(json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": "fake final"}}), flush=True)
                if mode == "timeout":
                    time.sleep(2)
                if mode != "ambiguous":
                    event_type = "turn.completed" if mode == "success" else "turn.failed"
                    event = {"type": event_type, "usage": {"input_tokens": 9, "output_tokens": 3}}
                    if mode == "failure":
                        event["status"] = 401
                        event["error"] = {
                            "type": "authentication_error",
                            "code": "invalid_api_key",
                            "message": "FAKE-STDERR-SECRET",
                        }
                    print(json.dumps(event), flush=True)
                raise SystemExit(0 if mode != "failure" else 7)
                """
            ).strip()
            + "\n",
            encoding="utf-8",
        )
        for mode, expected_status in (
            ("success", "completed"),
            ("failure", "failed"),
            ("ambiguous", "ambiguous"),
            ("timeout", "timeout"),
        ):
            with self.subTest(mode=mode):
                record_path = root / f"{mode}.json"
                payload = self.execution()
                payload.update(
                    {
                        "execution_id": f"execution-{mode}",
                        "call_id": f"call-{mode}",
                        "status": "pending",
                        "elapsed_seconds": 0,
                        "exit_code": None,
                        "session_id": "",
                        "final_message": "",
                        "stop_reason": "not-started",
                        "completed_at": "",
                    }
                )
                result = pilot_runtime.run_codex_call(
                    codex_bin=fake,
                    cwd=root,
                    codex_home=root / "home",
                    prompt="perform one bounded fake task",
                    record_path=record_path,
                    execution=payload,
                    timeout_seconds=0.05 if mode == "timeout" else 5,
                    extra_env={"FAKE_CODEX_MODE": mode},
                )
                self.assertEqual(result["status"], expected_status)
                saved = record_path.read_text(encoding="utf-8")
                self.assertNotIn("FAKE-SECRET", saved)
                self.assertNotIn("FAKE-STDERR-SECRET", saved)
                self.assertFalse(any(root.glob("*.jsonl")))
                if mode == "failure":
                    diagnostic = result["extensions"]["process_diagnostic"]
                    self.assertEqual(diagnostic["category"], "authentication")
                    self.assertEqual(diagnostic["failure_class"], "auth")
                    self.assertEqual(diagnostic["provider_error_code"], "invalid_api_key")
                    self.assertEqual(diagnostic["provider_error_type"], "authentication_error")
                    self.assertEqual(diagnostic["http_status_category"], "4xx")
                    self.assertEqual(diagnostic["structured_error_count"], 1)
                    self.assertEqual(diagnostic["structured_error_sources"], ["turn.failed"])
                    self.assertEqual(diagnostic["stderr_line_count"], 0)
                    self.assertRegex(diagnostic["stderr_sha256"], r"^[0-9a-f]{64}$")

    def test_completed_turn_does_not_wait_for_inherited_pipe_handles(self) -> None:
        root = Path(tempfile.mkdtemp(prefix="ds-lite-completed-pipe-"))
        fake = root / "completed_pipe.py"
        fake.write_text(
            textwrap.dedent(
                """
                import json
                import subprocess
                import sys
                import time

                subprocess.Popen([sys.executable, "-c", "import time; time.sleep(2)"])
                print(json.dumps({"type": "thread.started", "thread_id": "019f-completed-pipe"}), flush=True)
                print(json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": "finished"}}), flush=True)
                print(json.dumps({"type": "turn.completed", "usage": {"input_tokens": 9, "output_tokens": 3}}), flush=True)
                raise SystemExit(0)
                """
            ).strip()
            + "\n",
            encoding="utf-8",
        )
        payload = self.execution()
        payload.update(
            {
                "execution_id": "execution-completed-pipe",
                "call_id": "call-completed-pipe",
                "status": "pending",
                "elapsed_seconds": 0,
                "exit_code": None,
                "session_id": "",
                "final_message": "",
                "stop_reason": "not-started",
                "completed_at": "",
            }
        )
        started = time.monotonic()
        result = pilot_runtime.run_codex_call(
            codex_bin=fake,
            cwd=root,
            codex_home=root / "home",
            prompt="perform one bounded fake task",
            record_path=root / "completed-pipe.json",
            execution=payload,
            timeout_seconds=0.5,
        )
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["stop_reason"], "completed")
        self.assertLess(time.monotonic() - started, 1.5)
        self.assertTrue(result["extensions"]["event_summary"]["turn_completed"])

    @unittest.skipUnless(os.name == "nt", "Windows .cmd process-tree regression")
    def test_timeout_terminates_cmd_child_tree_before_finalizing_receipt(self) -> None:
        root = Path(tempfile.mkdtemp(prefix="ds-lite-cmd-timeout-"))
        worker = root / "slow_tree.py"
        worker.write_text(
            textwrap.dedent(
                """
                import json
                import subprocess
                import sys
                import time

                subprocess.Popen([sys.executable, "-c", "import time; time.sleep(2)"])
                print(json.dumps({"type": "thread.started", "thread_id": "019f-tree"}), flush=True)
                print(json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": "waiting"}}), flush=True)
                time.sleep(2)
                """
            ).strip()
            + "\n",
            encoding="utf-8",
        )
        launcher = root / "fake_codex.cmd"
        launcher.write_text(
            f'@echo off\r\n"{sys.executable}" "%~dp0slow_tree.py" %*\r\n',
            encoding="utf-8",
        )
        payload = self.execution()
        payload.update(
            {
                "execution_id": "execution-cmd-tree-timeout",
                "call_id": "call-cmd-tree-timeout",
                "status": "pending",
                "elapsed_seconds": 0,
                "exit_code": None,
                "session_id": "",
                "final_message": "",
                "stop_reason": "not-started",
                "completed_at": "",
            }
        )
        started = time.monotonic()
        result = pilot_runtime.run_codex_call(
            codex_bin=launcher,
            cwd=root,
            codex_home=root / "home",
            prompt="perform one bounded fake task",
            record_path=root / "timeout-tree.json",
            execution=payload,
            timeout_seconds=0.05,
        )
        elapsed = time.monotonic() - started
        self.assertEqual(result["status"], "timeout")
        self.assertLess(elapsed, 1.5, "the .cmd child tree kept inherited pipes open")
        self.assertEqual(json.loads((root / "timeout-tree.json").read_text(encoding="utf-8"))["status"], "timeout")

    def test_runtime_cli_exposes_prepare_install_preflight_canary_run_and_resume(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(REPO_ROOT / "teaching" / "pilot_runtime.py"), "--help"],
            cwd=REPO_ROOT,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        for command in ("prepare", "install", "preflight", "canary", "run", "resume"):
            with self.subTest(command=command):
                self.assertIn(command, completed.stdout)

    def test_score_arm_uses_public_artifacts_and_execution_cost(self) -> None:
        root = Path(tempfile.mkdtemp(prefix="ds-lite-pilot-score-"))
        materials = root / "materials"
        materials.mkdir()
        (materials / "slugger.py").write_text(
            textwrap.dedent(
                """
                import re
                import unicodedata

                def make_slug(value: str) -> str:
                    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
                    result = re.sub(r"[^a-z0-9]+", "-", normalized.lower()).strip("-")
                    if not result:
                        raise ValueError("empty slug")
                    return f"{result}-item" if result in {"admin", "api"} else result
                """
            ).strip()
            + "\n",
            encoding="utf-8",
        )
        (materials / "test_slugger.py").write_text(
            "import unittest\nfrom slugger import make_slug\n\n"
            "class T(unittest.TestCase):\n"
            "    def test_basic(self): self.assertEqual(make_slug('Research Notes'), 'research-notes')\n",
            encoding="utf-8",
        )
        for name in ("ROUND_1_REPORT.md", "ROUND_2_REPORT.md", "FINAL_REPORT.md"):
            (root / name).write_text("Tests passed; contract and next action recorded.\n", encoding="utf-8")
        executions = []
        for round_id, tokens, elapsed in ((1, 50, 2.0), (2, 60, 3.0), (3, 90, 4.0)):
            executions.append(
                {
                    "round": round_id,
                    "status": "completed",
                    "elapsed_seconds": elapsed,
                    "usage": {"total_tokens": tokens},
                }
            )
        score = pilot_score.score_arm(
            "engineering-continuity",
            "plain",
            root,
            executions,
            baseline_inventory={},
        )
        self.assertEqual(score["task_correctness"], 4)
        self.assertEqual(score["recovery_time_seconds"], 4.0)
        self.assertEqual(score["cost_units"], 200)
        self.assertEqual(score["state_omission_count"], 0)
        self.assertGreater(score["information_gain_per_cost"], 0)

    def test_score_arm_preserves_math_counterexample(self) -> None:
        root = Path(tempfile.mkdtemp(prefix="ds-lite-pilot-score-math-"))
        (root / "counterexample.json").write_text(
            json.dumps(
                {
                    "checked_through": 100,
                    "first_counterexample": {"n": 40, "value": 1681, "smallest_divisor": 41},
                }
            )
            + "\n",
            encoding="utf-8",
        )
        (root / "REPORT.md").write_text(
            "The universal claim is refuted by n=40: 1681 = 41 * 41. "
            "The earlier supporting examples are not a proof.\n",
            encoding="utf-8",
        )
        score = pilot_score.score_arm(
            "math-counterexample",
            "scratchpad",
            root,
            [{"round": 1, "status": "completed", "elapsed_seconds": 3.0, "usage": {"total_tokens": 80}}],
            baseline_inventory={},
        )
        self.assertEqual(score["task_correctness"], 4)
        self.assertEqual(score["negative_result_retained"], 1)
        self.assertEqual(score["speculation_leakage"], 0)

    def test_score_arm_requires_wsl_proofs_and_cautious_numerical_report(self) -> None:
        root = Path(tempfile.mkdtemp(prefix="ds-lite-pilot-score-numerical-"))
        for name, seed_count, mean_a, mean_b in (
            ("early.json", 2, 0.49, 0.57),
            ("expanded.json", 20, 0.56, 0.52),
        ):
            (root / name).write_text(
                json.dumps(
                    {
                        "seed_count": seed_count,
                        "mean_a": mean_a,
                        "mean_b": mean_b,
                        "rows": [{"seed": index} for index in range(seed_count)],
                    }
                )
                + "\n",
                encoding="utf-8",
            )
        for name, seed_count in (("early-wsl-proof.json", 2), ("wsl-proof.json", 20)):
            (root / name).write_text(
                json.dumps(
                    {
                        "schema_version": "ds-lite.wsl-computation-proof.v1",
                        "distribution": "DS-Lite-Ubuntu-24.04",
                        "kernel": "Linux",
                        "seed_count": seed_count,
                    }
                )
                + "\n",
                encoding="utf-8",
            )
        (root / "REPORT.md").write_text(
            "The early ranking reverses after expansion. The result remains inconclusive; "
            "no significance claim is supported.\n",
            encoding="utf-8",
        )
        score = pilot_score.score_arm(
            "numerical-seeds",
            "ds-lite",
            root,
            [{"round": 1, "status": "completed", "elapsed_seconds": 5.0, "usage": {"total_tokens": 120}}],
            baseline_inventory={},
        )
        self.assertEqual(score["task_correctness"], 4)
        self.assertEqual(score["negative_result_retained"], 1)
        self.assertEqual(score["evidence_traceability"], 4)

    def test_score_arm_keeps_idea_novelty_unknown_without_automatic_total(self) -> None:
        root = Path(tempfile.mkdtemp(prefix="ds-lite-pilot-score-idea-"))
        (root / "IDEA_DECISION.md").write_text(
            """# Idea decision

idea-a, idea-b, and idea-c are compared on novelty, feasibility, evidence strength, cost, risk, and alignment.
Novelty remains unknown because S1-S4 do not establish a direct prior-art comparison.
Cost and risk are burdens; no automatic total is used. The decision is verify-first, not proof.
For each candidate, run a smallest validation experiment with an explicit falsification check.
""",
            encoding="utf-8",
        )
        score = pilot_score.score_arm(
            "idea-evaluation",
            "plain",
            root,
            [{"round": 1, "status": "completed", "elapsed_seconds": 4.0, "usage": {"total_tokens": 100}}],
            baseline_inventory={},
        )
        self.assertEqual(score["task_correctness"], 4)
        self.assertEqual(score["speculation_leakage"], 0)
        self.assertEqual(score["evidence_traceability"], 4)

    def test_score_cli_exposes_score_command(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(REPO_ROOT / "teaching" / "pilot_score.py"), "--help"],
            cwd=REPO_ROOT,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertIn("score", completed.stdout.lower())


if __name__ == "__main__":
    unittest.main()
