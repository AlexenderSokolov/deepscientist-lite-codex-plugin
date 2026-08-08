import queue
import time
import unittest
import io
import json
from pathlib import Path
import sys

from teaching.app_server_continuation_acceptance import (
    _error_diagnostic,
    _formal_trust_state,
    _next_stdout_event,
    _notify,
    _thread_id,
    evaluate_session_control,
    evaluate_stop_first,
)
from teaching.app_server_continuation_fixture import REPO_ROOT


class FormalHookTrustTests(unittest.TestCase):
    def test_initialized_notification_has_no_request_identifier(self):
        process = type("Process", (), {"stdin": io.StringIO()})()
        _notify(process, "initialized")
        self.assertEqual(json.loads(process.stdin.getvalue()), {"method": "initialized"})

    def test_legacy_harness_leaves_model_selection_to_the_fresh_host(self):
        acceptance = (Path(__file__).resolve().parents[1] / "teaching" / "app_server_continuation_acceptance.py").read_text(encoding="utf-8")
        self.assertNotIn('"modelProvider": "custom"', acceptance)
        self.assertNotIn('"model": model', acceptance)

    def test_error_diagnostic_keeps_only_category_and_hash(self):
        diagnostic = _error_diagnostic({"message": "Provider request timed out"})
        self.assertEqual(diagnostic["category"], "provider")
        self.assertEqual(set(diagnostic), {"category", "recovery_class", "message_sha256"})
        self.assertNotIn("Provider", "".join(diagnostic.values()))

    def test_error_diagnostic_classifies_quota_as_user_action(self):
        diagnostic = _error_diagnostic({"message": "HTTP 402 quota exhausted"})
        self.assertEqual(diagnostic["recovery_class"], "awaiting-user-action")

    def test_error_diagnostic_classifies_server_overload_as_retryable(self):
        diagnostic = _error_diagnostic({"message": "", "info": {"serverOverloaded": {}}})
        self.assertEqual(diagnostic["recovery_class"], "retryable")

    def test_fixture_cli_can_resolve_the_repository_package(self):
        self.assertTrue((REPO_ROOT / "teaching" / "trusted_hook_fixture.py").is_file())
        fixture = (REPO_ROOT / "teaching" / "app_server_continuation_fixture.py").read_text(encoding="utf-8")
        self.assertIn("ds_lite_communication_audit.py", fixture)
        self.assertIn("'status': 'completed'", fixture)
        self.assertIn("ds-lite.stop-first-protocol.v1", fixture)
        self.assertIn("autonomy-controller-completed", fixture)
        self.assertIn("attempt Stop again", fixture)

    def test_formal_trust_state_retains_only_key_hash_pairs(self):
        response = {
            "result": {
                "data": [{
                    "hooks": [
                        {"key": "stop-hook", "currentHash": "stop-hash"},
                        {"key": "missing-hash"},
                        {"currentHash": "missing-key"},
                    ]
                }]
            }
        }
        self.assertEqual(_formal_trust_state(response), {"stop-hook": {"trusted_hash": "stop-hash"}})

    def test_invalid_thread_start_response_is_classified_without_raw_error(self):
        with self.assertRaisesRegex(RuntimeError, "thread-start"):
            _thread_id({"error": {"message": "provider detail must not be persisted"}})

    def test_stdout_deadline_returns_without_blocking(self):
        events: queue.Queue[str | None] = queue.Queue()
        self.assertEqual(_next_stdout_event(events, time.monotonic() - 1), "")

    def test_legacy_stop_first_never_counts_as_hook_in_turn_repair(self):
        status, failure = evaluate_stop_first(
            trust_ready=True,
            hook_counts={"stop:block": 1, "stop:allow": 1},
            summary_completed=True,
            terminal="turn/completed",
            continuation_observed=True,
        )
        self.assertEqual((status, failure), ("blocked", "legacy-stop-first-semantics"))
        status, failure = evaluate_stop_first(
            trust_ready=True,
            hook_counts={"stop:block": 1},
            summary_completed=False,
            terminal="turn/completed",
        )
        self.assertEqual((status, failure), ("blocked", "legacy-stop-first-semantics"))
        status, failure = evaluate_stop_first(
            trust_ready=True,
            hook_counts={"stop:block": 1},
            summary_completed=True,
            terminal="turn/completed",
        )
        self.assertEqual((status, failure), ("blocked", "legacy-stop-first-semantics"))

    def test_user_prompt_first_does_not_unlock_stop_first(self):
        status, failure = evaluate_session_control(
            trust_ready=True,
            hook_counts={"user-prompt-submit:allow": 1, "stop:allow": 1},
            summary_completed=True,
            terminal="turn/completed",
            error_count=0,
        )
        self.assertEqual((status, failure), ("passed", "none"))
        stop_status, stop_failure = evaluate_stop_first(
            trust_ready=True,
            hook_counts={"user-prompt-submit:allow": 1, "stop:allow": 1},
            summary_completed=True,
            terminal="turn/completed",
        )
        self.assertEqual((stop_status, stop_failure), ("blocked", "legacy-stop-first-semantics"))

    def test_core_autonomy_runner_uses_the_runtime_resolver(self):
        root = Path(__file__).resolve().parents[1] / "plugins" / "deepscientist-lite-core"
        runtime = (root / "assets" / "templates" / "tools" / "ds_lite_runtime.sh").read_text(encoding="utf-8")
        runner = (root / "assets" / "templates" / "run_autonomy.sh").read_text(encoding="utf-8")
        windows_runner = (root / "assets" / "templates" / "run_autonomy.ps1").read_text(encoding="utf-8")
        state = (root / "scripts" / "ds_lite_state.py").read_text(encoding="utf-8")
        self.assertIn("autonomy)", runtime)
        self.assertIn("ds_lite_autonomy.py", runtime)
        self.assertIn("ds_lite_cli autonomy", runner)
        self.assertIn("--resume", runner)
        self.assertIn("DS_LITE_PLUGIN_ROOT", windows_runner)
        self.assertIn("Join-Path $$Root", windows_runner)
        self.assertIn("run_autonomy.ps1", state)
        acceptance = (Path(__file__).resolve().parents[1] / "teaching" / "app_server_continuation_acceptance.py").read_text(encoding="utf-8")
        self.assertIn("--direct-egress", acceptance)
        self.assertIn("proxy_env_cleared", acceptance)
        self.assertIn("NO_PROXY", acceptance)
        scripts = root / "scripts"
        sys.path.insert(0, str(scripts))
        try:
            import ds_lite_state
            rendered = ds_lite_state.render_template("run_autonomy.ps1", {})
        finally:
            sys.path.remove(str(scripts))
        self.assertIn("$ErrorActionPreference", rendered)

    def test_legacy_harness_is_explicitly_nonpassing(self):
        acceptance = (Path(__file__).resolve().parents[1] / "teaching" / "app_server_continuation_acceptance.py").read_text(encoding="utf-8")
        self.assertIn('"ds-lite.legacy-stop-first-continuation.v1"', acceptance)
        self.assertIn('"legacy-stop-first-semantics"', acceptance)

    def test_legacy_harness_cannot_dispatch_a_second_turn(self):
        acceptance = (Path(__file__).resolve().parents[1] / "teaching" / "app_server_continuation_acceptance.py").read_text(encoding="utf-8")
        self.assertNotIn("Continue the same session and report the completed controller summary", acceptance)

    def test_app_server_launch_uses_current_default_stdio_transport(self):
        acceptance = (Path(__file__).resolve().parents[1] / "teaching" / "app_server_continuation_acceptance.py").read_text(encoding="utf-8")
        self.assertNotIn('[str(codex_bin), "app-server", "--stdio"]', acceptance)


if __name__ == "__main__":
    unittest.main()
