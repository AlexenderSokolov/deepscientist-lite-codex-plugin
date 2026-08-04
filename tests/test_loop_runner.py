import json
import hashlib
import os
import subprocess
import sys
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

from plugins.deepscientist_lite_import_shim import ds_lite_loop


class LoopRunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "plans").mkdir()
        (self.root / "plans" / "work.md").write_text("plan", encoding="utf-8")
        (self.root / "plans" / "prompt.md").write_text("prompt", encoding="utf-8")
        (self.root / "goals.json").write_text(json.dumps([
            {"id": "goal-a", "evidence_refs": ["evidence/a.txt"]},
            {"id": "goal-b", "evidence_refs": ["evidence/b.txt"]},
        ]), encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def prepare(self, *, adapter="fake", max_rounds=3, max_seconds=60,
                authorization="required", allowed_paths=None, approval_ref=None,
                output_name="loop.json"):
        output = self.root / output_name
        if approval_ref is None:
            approval_ref = "approvals/user.md" if authorization == "approved" else ""
        args = Namespace(loop_id="loop-test", goals_file=str(self.root / "goals.json"),
                         working_plan_ref="plans/work.md", prompt_ref="plans/prompt.md",
                         allowed_path=allowed_paths or ["evidence"], adapter=adapter, max_rounds=max_rounds,
                         max_seconds=max_seconds, authorization=authorization,
                         authority="user" if authorization == "approved" else "none",
                         approval_ref=approval_ref,
                         sandbox="read-only", output=str(output))
        ds_lite_loop.prepare(args)
        return output

    def run_fake(self, contract, sequence, *, run_name="run"):
        sequence_path = self.root / f"{run_name}-sequence.json"
        sequence_path.write_text(json.dumps(sequence), encoding="utf-8")
        args = Namespace(contract=str(contract), root=str(self.root), output_dir=str(self.root / run_name),
                         fake_sequence=str(sequence_path), codex_bin=None, autoresearch_bin=None, execute=False)
        return ds_lite_loop.run_loop(args)

    def approve(self):
        (self.root / "approvals").mkdir(exist_ok=True)
        (self.root / "approvals" / "user.md").write_text("approved", encoding="utf-8")

    def test_partial_then_completed_requires_all_evidence(self):
        contract = self.prepare()
        (self.root / "evidence").mkdir()
        (self.root / "evidence" / "a.txt").write_text("a", encoding="utf-8")
        (self.root / "evidence" / "b.txt").write_text("b", encoding="utf-8")
        summary = self.run_fake(contract, [
            {"status": "partial", "failure_layer": "none", "session_id": "s1"},
            {"status": "completed", "failure_layer": "none", "session_id": "s1", "completion": True,
             "completed_goal_ids": ["goal-a", "goal-b"]},
        ])
        self.assertEqual(summary["status"], "completed")
        self.assertEqual(summary["round_count"], 2)

    def test_completion_signal_without_evidence_is_blocked(self):
        contract = self.prepare()
        summary = self.run_fake(contract, [
            {"status": "completed", "failure_layer": "none", "completion": True,
             "completed_goal_ids": ["goal-a", "goal-b"]},
        ])
        self.assertEqual(summary["status"], "blocked")
        receipt = json.loads((self.root / "run" / "round-001.json").read_text(encoding="utf-8"))
        self.assertFalse(receipt["continuation_authorized"])
        self.assertTrue(receipt["missing_evidence"])

    def test_ambiguous_and_duplicate_risk_never_continue(self):
        contract = self.prepare()
        for index, failure in enumerate(("ambiguous", "duplicate-risk"), 1):
            with self.subTest(failure=failure):
                child = self.root / f"case-{index}"
                child.mkdir()
                sequence = child / "sequence.json"
                sequence.write_text(json.dumps([{"status": "partial", "failure_layer": failure}]), encoding="utf-8")
                result = ds_lite_loop.run_loop(Namespace(contract=str(contract), root=str(self.root),
                    output_dir=str(child / "run"), fake_sequence=str(sequence), codex_bin=None,
                    autoresearch_bin=None, execute=False))
                self.assertEqual(result["round_count"], 1)

    def test_real_adapter_requires_approval_and_execute(self):
        contract = self.prepare(adapter="native-codex")
        args = Namespace(contract=str(contract), root=str(self.root), output_dir=str(self.root / "run"),
                         fake_sequence=None, codex_bin="codex", autoresearch_bin=None, execute=False)
        with self.assertRaises(ds_lite_loop.LoopError):
            ds_lite_loop.run_loop(args)

    def test_contract_and_outputs_are_fresh_only(self):
        contract = self.prepare()
        with self.assertRaises(ds_lite_loop.LoopError):
            self.prepare()
        self.assertEqual(ds_lite_loop.validate_contract(json.loads(contract.read_text(encoding="utf-8")))["loop_id"], "loop-test")

    def test_secret_marker_from_fake_sequence_is_not_persisted(self):
        contract = self.prepare()
        summary = self.run_fake(contract, [{"status": "blocked", "failure_layer": "auth", "secret": "SECRET_MARKER"}])
        self.assertEqual(summary["status"], "blocked")
        persisted = "".join(path.read_text(encoding="utf-8") for path in (self.root / "run").glob("*.json"))
        self.assertNotIn("SECRET_MARKER", persisted)

    def test_time_budget_exhaustion_writes_terminal_freeze_receipt(self):
        contract = self.prepare(max_seconds=60)
        sequence = [
            {"status": "partial", "failure_layer": "none", "session_id": "s1"},
            {"status": "completed", "failure_layer": "none", "session_id": "s1", "completion": True,
             "completed_goal_ids": ["goal-a", "goal-b"]},
        ]
        with patch.object(ds_lite_loop.time, "monotonic", side_effect=[0.0, 0.0, 61.0]):
            summary = self.run_fake(contract, sequence)
        self.assertEqual(summary["status"], "blocked")
        self.assertEqual(summary["round_count"], 2)
        receipt = json.loads((self.root / "run" / "round-002.json").read_text(encoding="utf-8"))
        self.assertEqual(receipt["failure_layer"], "time-budget")
        self.assertFalse(receipt["continuation_authorized"])

    def test_verify_rejects_non_completed_summary_and_inconsistent_receipt_chain(self):
        contract = self.prepare()
        blocked = self.run_fake(contract, [{"status": "blocked", "failure_layer": "auth"}])
        result = ds_lite_loop.verify(Namespace(contract=str(contract), summary=str(self.root / "run" / "summary.json")))
        self.assertEqual(blocked["status"], "blocked")
        self.assertEqual(result["status"], "blocked")

        complete_contract = self.prepare(output_name="complete-loop.json")
        (self.root / "evidence").mkdir()
        (self.root / "evidence" / "a.txt").write_text("a", encoding="utf-8")
        (self.root / "evidence" / "b.txt").write_text("b", encoding="utf-8")
        self.run_fake(complete_contract, [{"status": "completed", "failure_layer": "none", "completion": True,
                                           "completed_goal_ids": ["goal-a", "goal-b"]}], run_name="complete-run")
        summary_path = self.root / "complete-run" / "summary.json"
        self.assertEqual(ds_lite_loop.verify(Namespace(contract=str(complete_contract), summary=str(summary_path)))["status"], "passed")
        receipt_path = self.root / "complete-run" / "round-001.json"
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        receipt["raw_stdout"] = "SECRET_MARKER"
        receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
        self.assertEqual(ds_lite_loop.verify(Namespace(contract=str(complete_contract), summary=str(summary_path)))["status"], "blocked")
        receipt.pop("raw_stdout")
        receipt["loop_id"] = "different-loop"
        receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
        self.assertEqual(ds_lite_loop.verify(Namespace(contract=str(complete_contract), summary=str(summary_path)))["status"], "blocked")

    def test_run_rejects_output_escape_and_missing_authorization_ref(self):
        contract = self.prepare()
        sequence = self.root / "sequence.json"
        sequence.write_text('[{"status":"blocked","failure_layer":"auth"}]', encoding="utf-8")
        with self.assertRaises(ds_lite_loop.LoopError):
            ds_lite_loop.run_loop(Namespace(contract=str(contract), root=str(self.root),
                output_dir=str(self.root.parent / f"{self.root.name}-escaped-run"), fake_sequence=str(sequence),
                codex_bin=None, autoresearch_bin=None, execute=False))

        approved = self.prepare(adapter="native-codex", authorization="approved", output_name="approved-loop.json")
        with self.assertRaises(ds_lite_loop.LoopError):
            ds_lite_loop.run_loop(Namespace(contract=str(approved), root=str(self.root),
                output_dir=str(self.root / "approved-run"), fake_sequence=None,
                codex_bin=str(self.root / "codex.exe"), autoresearch_bin=None, execute=True))

    def test_contract_rejects_authorization_ref_escape(self):
        with self.assertRaises(ds_lite_loop.LoopError):
            self.prepare(adapter="native-codex", authorization="approved", approval_ref="../approval.md")

    def test_v2_contract_requires_explicit_bounded_autonomy_controls(self):
        contract = self.prepare()
        payload = json.loads(contract.read_text(encoding="utf-8"))
        payload["schema_version"] = "ds-lite.loop-contract.v2"
        payload["extensions"] = {"autonomy": {"retry_policy": "exponential-3", "progress_required": True}}
        self.assertEqual(ds_lite_loop.validate_contract(payload)["schema_version"], "ds-lite.loop-contract.v2")
        payload["extensions"] = {}
        with self.assertRaises(ds_lite_loop.LoopError):
            ds_lite_loop.validate_contract(payload)

    def test_evidence_must_be_inside_an_allowed_path(self):
        contract = self.prepare(allowed_paths=["work"])
        (self.root / "evidence").mkdir()
        (self.root / "evidence" / "a.txt").write_text("a", encoding="utf-8")
        (self.root / "evidence" / "b.txt").write_text("b", encoding="utf-8")
        summary = self.run_fake(contract, [{"status": "completed", "failure_layer": "none", "completion": True,
                                            "completed_goal_ids": ["goal-a", "goal-b"]}])
        self.assertEqual(summary["status"], "blocked")
        receipt = json.loads((self.root / "run" / "round-001.json").read_text(encoding="utf-8"))
        self.assertIn("outside-allowed-path:evidence/a.txt", receipt["missing_evidence"])

    def test_native_adapter_requires_explicit_pinned_binary_without_path_fallback(self):
        self.approve()
        contract = self.prepare(adapter="native-codex", authorization="approved")
        with self.assertRaises(ds_lite_loop.LoopError):
            ds_lite_loop.run_loop(Namespace(contract=str(contract), root=str(self.root),
                output_dir=str(self.root / "native-run"), fake_sequence=None,
                codex_bin=None, autoresearch_bin=None, execute=True))

    def test_pinned_codex_validation_checks_sha_and_version(self):
        binary = self.root / "codex.exe"
        binary.write_bytes(b"pinned-binary")
        digest = hashlib.sha256(binary.read_bytes()).hexdigest().upper()
        version = subprocess.CompletedProcess([str(binary), "--version"], 0, "codex-cli 0.144.5\n", "")
        with patch.dict(os.environ, {"DS_LITE_CODEX_SHA256": digest}), \
             patch.object(ds_lite_loop.subprocess, "run", return_value=version):
            self.assertEqual(ds_lite_loop._validate_codex_binary(binary), binary.resolve())
        wrong_version = subprocess.CompletedProcess([str(binary), "--version"], 0, "codex-cli 0.128.0\n", "")
        with patch.dict(os.environ, {"DS_LITE_CODEX_SHA256": digest}), \
             patch.object(ds_lite_loop.subprocess, "run", return_value=wrong_version):
            with self.assertRaises(ds_lite_loop.LoopError):
                ds_lite_loop._validate_codex_binary(binary)

    def test_native_resume_requires_session_and_preserves_json_sandbox_flags(self):
        self.approve()
        contract = self.prepare(adapter="native-codex", authorization="approved")
        (self.root / "plans" / "prompt.md").write_text("TOP_SECRET_PROMPT", encoding="utf-8")
        (self.root / "evidence").mkdir()
        (self.root / "evidence" / "a.txt").write_text("a", encoding="utf-8")
        (self.root / "evidence" / "b.txt").write_text("b", encoding="utf-8")
        observations = [
            {"process_started": True, "returncode_observed": True, "returncode": 0, "session_id": "session-1",
             "result": {"status": "partial", "goal_ids": ["goal-a"]}, "completion": None,
             "terminal_event_observed": True, "failure_layer": "none"},
            {"process_started": True, "returncode_observed": True, "returncode": 0, "session_id": "session-1",
             "result": {"status": "completed", "goal_ids": ["goal-a", "goal-b"]},
             "completion": {"status": "completed", "goal_ids": ["goal-a", "goal-b"]},
             "terminal_event_observed": True, "failure_layer": "none"},
        ]
        commands = []
        inputs = []
        def capture(command, cwd, timeout, input_text=None):
            commands.append(command)
            inputs.append(input_text)
            return observations[len(commands) - 1]
        with patch.object(ds_lite_loop, "_validate_codex_binary", return_value=self.root / "codex.exe"), \
             patch.object(ds_lite_loop, "_run_process", side_effect=capture):
            summary = ds_lite_loop.run_loop(Namespace(contract=str(contract), root=str(self.root),
                output_dir=str(self.root / "native-run"), fake_sequence=None,
                codex_bin=str(self.root / "codex.exe"), autoresearch_bin=None, execute=True))
        self.assertEqual(summary["status"], "completed")
        self.assertEqual(len(commands), 2)
        resume = commands[1]
        self.assertEqual(resume[:5], [str(self.root / "codex.exe"), "exec", "-C", str(self.root), "resume"])
        for expected in ("session-1", "--json", "-c", 'sandbox_mode="read-only"', "--skip-git-repo-check", "-C"):
            self.assertIn(expected, resume)
        self.assertNotIn("--sandbox", resume)
        self.assertEqual(commands[0][-1], "-")
        self.assertEqual(commands[1][-1], "-")
        self.assertNotIn("TOP_SECRET_PROMPT", " ".join(commands[0]))
        self.assertIn("TOP_SECRET_PROMPT", inputs[0])
        self.assertIn("DS_LITE_LOOP_RESULT", inputs[0])
        self.assertIn("DS_LITE_LOOP_RESULT", inputs[1])
        self.assertIn(json.loads(contract.read_text(encoding="utf-8"))["frozen_goal_digest"], inputs[0])
        persisted = "".join(path.read_text(encoding="utf-8") for path in (self.root / "native-run").glob("*.json"))
        self.assertNotIn("TOP_SECRET_PROMPT", persisted)
        self.assertNotIn(str(self.root), persisted)

    def test_native_partial_without_session_freezes_before_resume(self):
        self.approve()
        contract = self.prepare(adapter="native-codex", authorization="approved")
        observation = {"process_started": True, "returncode_observed": True, "returncode": 0, "session_id": "",
                       "result": {"status": "partial", "goal_ids": ["goal-a"]}, "completion": None,
                       "terminal_event_observed": True, "failure_layer": "none"}
        with patch.object(ds_lite_loop, "_validate_codex_binary", return_value=self.root / "codex.exe"), \
             patch.object(ds_lite_loop, "_run_process", return_value=observation) as run:
            summary = ds_lite_loop.run_loop(Namespace(contract=str(contract), root=str(self.root),
                output_dir=str(self.root / "native-run"), fake_sequence=None,
                codex_bin=str(self.root / "codex.exe"), autoresearch_bin=None, execute=True))
        self.assertEqual(summary["status"], "blocked")
        self.assertEqual(summary["round_count"], 1)
        self.assertEqual(run.call_count, 1)
        receipt = json.loads((self.root / "native-run" / "round-001.json").read_text(encoding="utf-8"))
        self.assertEqual(receipt["failure_layer"], "protocol")

    def test_process_accepts_only_structured_allowlisted_terminal_completion(self):
        plain = self.root / "plain.py"
        plain.write_text('print(\'DS_LITE_LOOP_COMPLETION {"status":"completed","goal_ids":["goal-a","goal-b"]} SECRET_MARKER\')\n', encoding="utf-8")
        plain_result = ds_lite_loop._run_process([sys.executable, str(plain)], self.root, 10)
        self.assertIsNone(plain_result["completion"])
        self.assertNotIn("SECRET_MARKER", json.dumps(plain_result))

        structured = self.root / "structured.py"
        structured.write_text(
            'import json\n'
            'print(json.dumps({"type":"item.completed","item":{"id":"item_0","type":"agent_message","text":"DS_LITE_LOOP_RESULT {\\"status\\":\\"completed\\",\\"goal_ids\\":[\\"goal-a\\",\\"goal-b\\"]}"}}))\n'
            'print(json.dumps({"type":"turn.completed","usage":{"input_tokens":1,"output_tokens":1}}))\n',
            encoding="utf-8",
        )
        structured_result = ds_lite_loop._run_process([sys.executable, str(structured)], self.root, 10)
        self.assertEqual(structured_result["completion"]["goal_ids"], ["goal-a", "goal-b"])

        stderr_only = self.root / "stderr-structured.py"
        stderr_only.write_text(
            'import json, sys\n'
            'sys.stderr.write(json.dumps({"type":"item.completed","item":{"type":"agent_message","text":"DS_LITE_LOOP_RESULT {\\"status\\":\\"completed\\",\\"goal_ids\\":[\\"goal-a\\",\\"goal-b\\"]}"}}) + "\\n")\n'
            'sys.stderr.write(json.dumps({"type":"turn.completed"}) + "\\n")\n',
            encoding="utf-8",
        )
        stderr_result = ds_lite_loop._run_process([sys.executable, str(stderr_only)], self.root, 10)
        self.assertIsNone(stderr_result["completion"])

    def test_completion_requires_agent_message_candidate_then_turn_completed(self):
        marker = 'DS_LITE_LOOP_RESULT {"status":"completed","goal_ids":["goal-a","goal-b"]}'
        item = json.dumps({"type": "item.completed", "item": {"id": "item_0", "type": "agent_message", "text": marker}})
        terminal = json.dumps({"type": "turn.completed", "usage": {"input_tokens": 1, "output_tokens": 1}})
        reduced = ds_lite_loop._reduce_jsonl(item + "\n" + terminal + "\n")
        self.assertEqual(reduced["completion"], {"status": "completed", "goal_ids": ["goal-a", "goal-b"]})
        self.assertTrue(reduced["terminal_event_observed"])

    def test_completion_rejects_wrong_item_shape_text_and_missing_terminal(self):
        marker = 'DS_LITE_LOOP_RESULT {"status":"completed","goal_ids":["goal-a","goal-b"]}'
        cases = {
            "reasoning": [
                {"type": "item.completed", "item": {"type": "reasoning", "text": marker}},
                {"type": "turn.completed"},
            ],
            "command-output": [
                {"type": "item.completed", "item": {"type": "command_execution", "aggregated_output": marker}},
                {"type": "turn.completed"},
            ],
            "ordinary-text": [
                {"type": "item.completed", "item": {"type": "agent_message", "text": "done " + marker}},
                {"type": "turn.completed"},
            ],
            "multiline-text": [
                {"type": "item.completed", "item": {"type": "agent_message", "text": marker + "\nextra"}},
                {"type": "turn.completed"},
            ],
            "trailing-whitespace": [
                {"type": "item.completed", "item": {"type": "agent_message", "text": marker + " "}},
                {"type": "turn.completed"},
            ],
            "no-terminal": [
                {"type": "item.completed", "item": {"type": "agent_message", "text": marker}},
            ],
            "top-level-forgery": [
                {"type": "turn.completed", "ds_lite_loop_completion": {"status": "completed", "goal_ids": ["goal-a", "goal-b"]}},
            ],
        }
        for name, events in cases.items():
            with self.subTest(name=name):
                reduced = ds_lite_loop._reduce_jsonl("\n".join(json.dumps(event) for event in events) + "\n")
                self.assertIsNone(reduced["completion"])

    def test_completion_candidate_is_discarded_on_failure_or_conflict(self):
        first = 'DS_LITE_LOOP_RESULT {"status":"completed","goal_ids":["goal-a","goal-b"]}'
        conflict = 'DS_LITE_LOOP_RESULT {"status":"completed","goal_ids":["goal-a"]}'
        candidate = {"type": "item.completed", "item": {"type": "agent_message", "text": first}}
        conflicting = {"type": "item.completed", "item": {"type": "agent_message", "text": conflict}}
        for terminal in ({"type": "turn.failed", "error": {}}, {"type": "error"}):
            with self.subTest(terminal=terminal["type"]):
                reduced = ds_lite_loop._reduce_jsonl(json.dumps(candidate) + "\n" + json.dumps(terminal) + "\n")
                self.assertIsNone(reduced["completion"])
        conflict_stream = "\n".join(json.dumps(event) for event in (candidate, conflicting, {"type": "turn.completed"})) + "\n"
        self.assertIsNone(ds_lite_loop._reduce_jsonl(conflict_stream)["completion"])

    def test_turn_completed_without_result_payload_is_protocol_failure(self):
        script = self.root / "missing-result.py"
        script.write_text('import json\nprint(json.dumps({"type":"turn.completed","usage":{}}))\n', encoding="utf-8")
        result = ds_lite_loop._run_process([sys.executable, str(script)], self.root, 10)
        self.assertEqual(result["failure_layer"], "protocol")
        self.assertIsNone(result["result"])

    def test_partial_result_requires_terminal_and_is_structured(self):
        marker = 'DS_LITE_LOOP_RESULT {"status":"partial","goal_ids":["goal-a"]}'
        stream = "\n".join((
            json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": marker}}),
            json.dumps({"type": "turn.completed"}),
        )) + "\n"
        reduced = ds_lite_loop._reduce_jsonl(stream)
        self.assertEqual(reduced["result"], {"status": "partial", "goal_ids": ["goal-a"]})
        self.assertIsNone(reduced["completion"])

    def test_strict_terminal_result_outweighs_incidental_authorization_text(self):
        script = self.root / "successful-partial-with-diagnostic.py"
        script.write_text(
            'import json, sys\n'
            'sys.stderr.write("tool note: authorization boundary checked\\n")\n'
            'print(json.dumps({"type":"thread.started","thread_id":"session-1"}))\n'
            'print(json.dumps({"type":"item.completed","item":{"type":"agent_message","text":"DS_LITE_LOOP_RESULT {\\"status\\":\\"partial\\",\\"goal_ids\\":[\\"goal-a\\"]}"}}))\n'
            'print(json.dumps({"type":"turn.completed"}))\n',
            encoding="utf-8",
        )
        result = ds_lite_loop._run_process([sys.executable, str(script)], self.root, 10)
        self.assertEqual(result["failure_layer"], "none")
        self.assertEqual(result["result"], {"status": "partial", "goal_ids": ["goal-a"]})

    def test_spawn_and_child_early_exit_are_fail_closed(self):
        spawn = ds_lite_loop._run_process([str(self.root / "missing-command.exe")], self.root, 10)
        self.assertEqual(spawn["failure_layer"], "child-process")
        self.assertEqual(spawn["child_process_state"], "spawn-failed")

        early = self.root / "early.py"
        early.write_text("raise SystemExit(3)\n", encoding="utf-8")
        child = ds_lite_loop._run_process([sys.executable, str(early)], self.root, 10)
        self.assertEqual(child["failure_layer"], "child-process")
        self.assertEqual(child["child_process_state"], "early-exit")

    def test_completion_goal_ids_must_exactly_equal_frozen_ids(self):
        contract = self.prepare()
        (self.root / "evidence").mkdir()
        (self.root / "evidence" / "a.txt").write_text("a", encoding="utf-8")
        (self.root / "evidence" / "b.txt").write_text("b", encoding="utf-8")
        for index, ids in enumerate((["goal-a", "goal-b", "extra"], ["goal-a", "goal-a", "goal-b"]), 1):
            with self.subTest(ids=ids):
                summary = self.run_fake(contract, [{"status": "completed", "failure_layer": "none", "completion": True,
                                                     "completed_goal_ids": ids}], run_name=f"exact-{index}")
                self.assertEqual(summary["status"], "blocked")

    def test_status_uses_derived_allowlisted_fields_only(self):
        summary = self.root / "malicious-summary.json"
        summary.write_text(json.dumps({"schema_version": ds_lite_loop.SUMMARY_SCHEMA, "loop_id": "loop-test",
                                       "status": "blocked", "round_count": 1, "next_action": "SECRET_MARKER"}), encoding="utf-8")
        result = ds_lite_loop.status(Namespace(summary=str(summary)))
        self.assertEqual(result["next_action"], "inspect-terminal-receipt")
        self.assertNotIn("SECRET_MARKER", json.dumps(result))

    def test_autoresearch_adapter_uses_the_same_pinned_resume_contract(self):
        self.approve()
        contract = self.prepare(adapter="codex-autoresearch", authorization="approved")
        (self.root / "evidence").mkdir()
        (self.root / "evidence" / "a.txt").write_text("a", encoding="utf-8")
        (self.root / "evidence" / "b.txt").write_text("b", encoding="utf-8")
        observations = [
            {"process_started": True, "returncode_observed": True, "session_id": "session-1", "result": {"status": "partial", "goal_ids": ["goal-a"]}, "completion": None, "terminal_event_observed": True, "failure_layer": "none"},
            {"process_started": True, "returncode_observed": True, "session_id": "session-1", "result": {"status": "completed", "goal_ids": ["goal-a", "goal-b"]}, "completion": {"status": "completed", "goal_ids": ["goal-a", "goal-b"]}, "terminal_event_observed": True, "failure_layer": "none"},
        ]
        with patch.object(ds_lite_loop, "_validate_codex_binary", return_value=self.root / "codex.exe"), \
             patch.object(ds_lite_loop, "_validate_autoresearch_binary", return_value=self.root / "codex-autoresearch.exe"), \
             patch.object(ds_lite_loop, "_run_process", side_effect=observations) as process:
            summary = ds_lite_loop.run_loop(Namespace(contract=str(contract), root=str(self.root),
                output_dir=str(self.root / "external-run"), fake_sequence=None,
                codex_bin=str(self.root / "codex.exe"), autoresearch_bin=str(self.root / "codex-autoresearch.exe"), execute=True))
        self.assertEqual(summary["status"], "completed")
        self.assertEqual(process.call_count, 2)

    def test_pipe_failure_is_reduced_without_raising_or_persisting_output(self):
        class BrokenPipeProcess:
            stdout = object()
            stderr = object()
            returncode = None

            def communicate(self, timeout=None):
                raise ValueError("SECRET_MARKER pipe broke")

        with patch.object(ds_lite_loop.subprocess, "Popen", return_value=BrokenPipeProcess()):
            result = ds_lite_loop._run_process(["unused"], self.root, 10)
        self.assertEqual(result["failure_layer"], "child-process")
        self.assertEqual(result["child_process_state"], "pipe-failed")
        self.assertNotIn("SECRET_MARKER", json.dumps(result))

    def test_untrusted_session_id_is_not_forwarded_to_resume_argv(self):
        reduced = ds_lite_loop._reduce_jsonl(
            '{"type":"thread.started","thread_id":"--dangerously-bypass-approvals-and-sandbox"}\n'
            '{"type":"turn.completed"}\n'
        )
        self.assertEqual(reduced["session_id"], "")

    def test_max_rounds_freezes_last_partial_receipt(self):
        contract = self.prepare(max_rounds=1)
        summary = self.run_fake(contract, [{"status": "partial", "failure_layer": "none"}])
        self.assertEqual(summary["status"], "blocked")
        receipt = json.loads((self.root / "run" / "round-001.json").read_text(encoding="utf-8"))
        self.assertEqual(receipt["failure_layer"], "round-budget")
        self.assertFalse(receipt["continuation_authorized"])


if __name__ == "__main__":
    unittest.main()
