from __future__ import annotations

import hashlib
import importlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
CONTROLLER_ROOT = ROOT / "plugins" / "deepscientist-lite-core" / "controller"
sys.path.insert(0, str(CONTROLLER_ROOT))

from ds_lite_control.cli import build_parser, doctor_report
from ds_lite_control.dbos_bridge import PHASE4_WORKFLOW_NAMES
from ds_lite_control.workflows import WORKFLOW_REGISTRY
from ds_lite_control.evidence import EvidenceManager
from ds_lite_control.release import GateDecisionEngine, StrictReleaseAggregate
from ds_lite_control.review import ReviewCoordinator
from ds_lite_control.store import ControlStore
from ds_lite_control.verification import DeterministicVerifier
from tools.validation.formal_release_gate import (
    COMPLETE_GATE_SCHEMAS, COMPLETE_PROFILE, SCHEMA_V2, evaluate,
)


class Phase5RuntimePinTests(unittest.TestCase):
    def test_real_broker_smoke_accepts_only_the_explicit_codex_version(self) -> None:
        module = importlib.import_module("teaching.controller_broker_smoke")
        self.assertTrue(module.version_matches("codex-cli 0.146.0", "0.146.0"))
        self.assertFalse(module.version_matches("codex-cli 0.128.0", "0.146.0"))

    def _schema_fixture(self, root: Path, version: str = "0.146.0") -> Path:
        schema_root = root / version
        schema_root.mkdir()
        bundle = schema_root / "protocol.json"
        bundle.write_text('{"schema":"stable"}\n', encoding="utf-8")
        digest = hashlib.sha256(bundle.read_bytes()).hexdigest()
        (schema_root / "SCHEMA-MANIFEST.json").write_text(
            json.dumps({
                "schema_version": "ds-lite.codex-schema-pin.v1",
                "codex_version": version,
                "platform": "windows-x86_64",
                "files": {"protocol.json": digest},
            }),
            encoding="utf-8",
        )
        return schema_root

    def test_runtime_pin_module_verifies_manifest_and_detects_drift(self) -> None:
        module = importlib.import_module("ds_lite_control.runtime_pin")
        with tempfile.TemporaryDirectory(prefix="ds-lite-phase5-pin-") as directory:
            schema_root = self._schema_fixture(Path(directory))
            observed = module.verify_schema_bundle(
                schema_root, expected_version="0.146.0", expected_platform="windows-x86_64"
            )
            self.assertTrue(observed["valid"])
            self.assertEqual(observed["codex_version"], "0.146.0")
            self.assertEqual(len(observed["manifest_digest"]), 64)
            (schema_root / "protocol.json").write_text("drift\n", encoding="utf-8")
            drifted = module.verify_schema_bundle(
                schema_root, expected_version="0.146.0", expected_platform="windows-x86_64"
            )
            self.assertFalse(drifted["valid"])
            self.assertIn("protocol.json", drifted["drifted_files"])

    def test_repository_contains_verified_stable_schema_pin(self) -> None:
        module = importlib.import_module("ds_lite_control.runtime_pin")
        pins = (
            ("0.146.0", "windows-x86_64"),
            ("0.146.0-linux-x86_64", "linux-x86_64"),
        )
        for directory, platform_name in pins:
            with self.subTest(platform=platform_name):
                schema_root = (
                    ROOT / "plugins" / "deepscientist-lite-core" / "schemas" / "codex" / directory
                )
                observed = module.verify_schema_bundle(
                    schema_root, expected_version="0.146.0", expected_platform=platform_name
                )
                self.assertTrue(observed["valid"], observed)
                self.assertEqual(observed["missing_files"], [])
                self.assertEqual(observed["drifted_files"], [])

    def test_doctor_requires_selected_binary_and_matching_schema(self) -> None:
        parsed = build_parser().parse_args([
            "doctor", "--project", ".", "--codex-bin", "codex.exe",
            "--schema-root", "schemas/0.146.0", "--codex-version", "0.146.0",
            "--codex-platform", "windows-x86_64",
        ])
        self.assertEqual(parsed.codex_version, "0.146.0")
        self.assertEqual(parsed.codex_platform, "windows-x86_64")
        matched = doctor_report(
            python_version="3.13.5", dbos_version="2.29.0", schema_version=4,
            integrity="ok", codex_schema_digest="a" * 64,
            expected_codex_schema_digest="a" * 64,
            codex_binary_version="0.146.0", expected_codex_version="0.146.0",
        )
        drifted = doctor_report(
            python_version="3.13.5", dbos_version="2.29.0", schema_version=4,
            integrity="ok", codex_schema_digest="b" * 64,
            expected_codex_schema_digest="a" * 64,
            codex_binary_version="0.146.0-alpha.9.2", expected_codex_version="0.146.0",
        )
        self.assertTrue(matched["managed_allowed"])
        self.assertFalse(drifted["managed_allowed"])
        self.assertFalse(drifted["checks"]["codex_binary"])
        self.assertFalse(drifted["checks"]["codex_schema"])

    def test_doctor_rejects_invalid_manifest_even_when_bundle_digest_matches(self) -> None:
        report = doctor_report(
            python_version="3.13.5", dbos_version="2.29.0", schema_version=4,
            integrity="ok", codex_schema_digest="a" * 64,
            expected_codex_schema_digest="a" * 64,
            codex_binary_version="0.146.0", expected_codex_version="0.146.0",
            codex_schema_valid=False,
        )
        self.assertFalse(report["managed_allowed"])
        self.assertFalse(report["checks"]["codex_schema"])

    def test_linux_python312_dependency_lock_is_platform_specific(self) -> None:
        lock = (
            ROOT / "plugins" / "deepscientist-lite-core" / "controller"
            / "requirements-linux-py312.lock"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "dbos==2.29.0 --hash=sha256:49104b64b8917dc3d321704f1d20058486c86129420b96b910f1e725fbdebca6",
            lock,
        )
        self.assertIn("greenlet==3.2.5", lock)
        self.assertNotIn("greenlet==3.5.4", lock)
        self.assertIn(
            "websockets==17.0 --hash=sha256:0c24d62cafaca7dc1631e9f3bf0672fa83f010e66a2aeff4d00727b18addcd8e",
            lock,
        )
        entries = [line for line in lock.splitlines() if line and not line.startswith("#")]
        self.assertTrue(entries)
        self.assertTrue(all(len(line.rsplit("sha256:", 1)[-1]) == 64 for line in entries))

    def test_windows_python313_dependency_lock_has_exact_sha256_values(self) -> None:
        lock = (
            ROOT / "plugins" / "deepscientist-lite-core" / "controller"
            / "requirements.lock"
        ).read_text(encoding="utf-8")
        entries = [line for line in lock.splitlines() if line and not line.startswith("#")]
        self.assertTrue(entries)
        self.assertTrue(all(len(line.rsplit("sha256:", 1)[-1]) == 64 for line in entries))

    def test_doctor_allows_verified_linux_python_only_for_linux_pin(self) -> None:
        linux = doctor_report(
            python_version="3.12.3", dbos_version="2.29.0", schema_version=4,
            integrity="ok", codex_schema_digest="a" * 64,
            expected_codex_schema_digest="a" * 64,
            codex_binary_version="0.146.0", expected_codex_version="0.146.0",
            codex_schema_valid=True, runtime_platform="linux-x86_64",
        )
        wrong_platform = doctor_report(
            python_version="3.12.3", dbos_version="2.29.0", schema_version=4,
            integrity="ok", codex_schema_digest="a" * 64,
            expected_codex_schema_digest="a" * 64,
            codex_binary_version="0.146.0", expected_codex_version="0.146.0",
            codex_schema_valid=True, runtime_platform="windows-x86_64",
        )
        self.assertTrue(linux["managed_allowed"])
        self.assertFalse(wrong_platform["managed_allowed"])

    def test_hook_smoke_digests_the_selected_generated_schema_bundle(self) -> None:
        module = importlib.import_module("teaching.hook_in_turn_repair_smoke")
        with tempfile.TemporaryDirectory(prefix="ds-lite-phase5-hook-schema-") as directory:
            root = Path(directory)
            bundle = root / "codex_app_server_protocol.v2.schemas.json"
            bundle.write_text('{"version":"stable"}\n', encoding="utf-8")
            self.assertEqual(module._schema_digest(root), hashlib.sha256(bundle.read_bytes()).hexdigest())

    def test_hook_smoke_projects_trust_status_without_source_paths(self) -> None:
        module = importlib.import_module("teaching.hook_in_turn_repair_smoke")
        summary = module._hook_summary({"data": [{
            "errors": [], "warnings": [], "hooks": [{
                "pluginId": "deepscientist-lite", "enabled": True,
                "eventName": "stop", "source": "plugin", "trustStatus": "trusted",
                "sourcePath": "private-path",
            }],
        }]}, "deepscientist-lite")
        self.assertEqual(summary["trust_counts"], {"trusted": 1})
        self.assertNotIn("sourcePath", json.dumps(summary))

    def test_hook_smoke_uses_only_the_isolated_vetted_trust_bypass(self) -> None:
        module = importlib.import_module("teaching.hook_in_turn_repair_smoke")
        command = module._hook_app_server_command(Path("codex.exe"))
        self.assertIn("--dangerously-bypass-hook-trust", command)
        self.assertNotIn("plugin_hooks", command)
        self.assertLess(command.index("--dangerously-bypass-hook-trust"), command.index("app-server"))

    def test_fresh_cli_places_hook_trust_bypass_before_exec(self) -> None:
        module = importlib.import_module("teaching.fresh_host_probe")
        command = module._exec_command_prefix(Path("codex.exe"), bypass_hook_trust=True)
        self.assertLess(command.index("--dangerously-bypass-hook-trust"), command.index("exec"))

    def test_trusted_hook_verifier_requires_one_turn_and_ordered_stop_repair(self) -> None:
        module = importlib.import_module("teaching.trusted_hook_run")
        receipt = {
            "status": "passed",
            "cli_identity": {"enforced": True, "expected_version": "0.146.0", "sha256_match": True},
            "event_type_counts": {"thread.started": 1, "turn.started": 1, "turn.completed": 1},
            "terminal_event_observed": True,
            "hook_event_sequence": [
                {"event_type": "user-prompt-submit", "decision": "allow",
                 "reason_present": False, "stop_hook_active": False},
                {"event_type": "stop", "decision": "block",
                 "reason_present": True, "stop_hook_active": False},
                {"event_type": "stop", "decision": "allow",
                 "reason_present": True, "stop_hook_active": True},
            ],
        }
        result = module.evaluate_hook_continuation(receipt)
        self.assertEqual(result["status"], "passed")
        self.assertTrue(result["checks"]["same_cli_turn_repair"])
        duplicate = dict(receipt, event_type_counts={"turn.started": 2, "turn.completed": 1})
        self.assertEqual(module.evaluate_hook_continuation(duplicate)["status"], "failed")

    def test_trusted_hook_verification_receipt_is_exclusive_create(self) -> None:
        module = importlib.import_module("teaching.trusted_hook_run")
        with tempfile.TemporaryDirectory(prefix="ds-lite-hook-verifier-") as directory:
            root = Path(directory)
            binary = root / "codex.exe"
            binary.write_bytes(b"stable")
            for name in ("home", "workspace", "events"):
                (root / name).mkdir()
            output = root / "host.json"
            verification = root / "verification.json"
            host_receipt = {
                "status": "passed", "failure_layer": "none",
                "cli_identity": {"enforced": True, "sha256_match": True},
                "event_type_counts": {"turn.started": 1, "turn.completed": 1},
                "terminal_event_observed": True,
                "hook_event_sequence": [
                    {"event_type": "stop", "decision": "block", "reason_present": True,
                     "stop_hook_active": False},
                    {"event_type": "stop", "decision": "allow", "reason_present": True,
                     "stop_hook_active": True},
                ],
                "hook_events": [],
            }
            expected_hash = hashlib.sha256(binary.read_bytes()).hexdigest()
            argv = [
                "--codex-bin", str(binary), "--codex-home", str(root / "home"),
                "--workspace", str(root / "workspace"), "--hook-events", str(root / "events"),
                "--output", str(output), "--verification-output", str(verification),
                "--prompt", "p", "--expected-version", "0.146.0",
                "--expected-sha256", expected_hash,
            ]
            with mock.patch.object(module, "run_once", return_value=host_receipt) as run_once:
                self.assertEqual(module.main(argv), 0)
                self.assertTrue(run_once.call_args.kwargs["codex_bin"].is_absolute())
                self.assertTrue(run_once.call_args.kwargs["codex_home"].is_absolute())
                self.assertTrue(run_once.call_args.kwargs["workspace"].is_absolute())
                self.assertTrue(run_once.call_args.kwargs["hook_events_path"].is_absolute())
                self.assertTrue(run_once.call_args.kwargs["output_path"].is_absolute())
                with self.assertRaises(FileExistsError):
                    module.main(argv)


class Phase5WorkflowRoutingTests(unittest.TestCase):
    def test_phase5_registry_is_additive_and_routes_new_actions_to_v2(self) -> None:
        bridge = importlib.import_module("ds_lite_control.dbos_bridge")
        workflows = importlib.import_module("ds_lite_control.workflows")
        self.assertEqual(bridge.PHASE5_WORKFLOW_NAMES[:-1], PHASE4_WORKFLOW_NAMES)
        self.assertEqual(bridge.PHASE5_WORKFLOW_NAMES[-1], "run_codex_action_v2")
        self.assertEqual(WORKFLOW_REGISTRY["run_codex_action_v1"]["version"], 1)
        self.assertEqual(WORKFLOW_REGISTRY["run_codex_action_v2"]["version"], 2)
        self.assertEqual(
            workflows.workflow_kind_for_action("codex-turn", existing="run_codex_action_v1"),
            "run_codex_action_v1",
        )
        self.assertEqual(
            workflows.workflow_kind_for_action("codex-turn-v2"),
            "run_codex_action_v2",
        )

    def test_v2_workflow_has_a_distinct_stable_runtime_boundary(self) -> None:
        bridge = importlib.import_module("ds_lite_control.dbos_bridge")
        self.assertEqual(bridge.PHASE5_CODEX_VERSION, "0.146.0")
        self.assertIsNot(bridge._run_codex_action_v2_body, bridge._run_codex_action_body)

    def test_real_v2_gate_requires_one_identity_and_terminal_host_event(self) -> None:
        module = importlib.import_module("teaching.control_plane_phase5_real_host")
        passed = module.evaluate_v2_observation(
            runtime_pin_valid=True, action_id="action-1", workflow_id="action-1",
            workflow_rows=1, terminal_status="completed", terminal_host_events=1,
            canonical_thread_count=1, turn_start_count=1, bootstrap_terminal=True,
        )
        self.assertEqual(passed["status"], "passed")
        duplicate = module.evaluate_v2_observation(
            runtime_pin_valid=True, action_id="action-1", workflow_id="replacement",
            workflow_rows=2, terminal_status="completed", terminal_host_events=1,
            canonical_thread_count=1, turn_start_count=2, bootstrap_terminal=False,
        )
        self.assertEqual(duplicate["status"], "failed")
        self.assertFalse(duplicate["checks"]["single_action_workflow_identity"])

    def test_v2_resumes_the_bound_thread_before_dispatch(self) -> None:
        bridge = importlib.import_module("ds_lite_control.dbos_bridge")
        with mock.patch(
            "ds_lite_control.runtime_pin.verify_runtime_selection",
            return_value={"valid": True},
        ), mock.patch.object(
            bridge, "_run_codex_action_common", return_value={"terminal_status": "completed"},
        ) as common:
            result = bridge._run_codex_action_v2_body(
                "action", "domain", "owner", 1, "codex", "schema", "home",
                "spool", [{"type": "text", "text": "ok"}], 10.0,
                "windows-x86_64",
            )
        self.assertEqual(result["terminal_status"], "completed")
        self.assertTrue(common.call_args.kwargs["resume_bound_thread"])


class Phase5ResourceEvaluationTests(unittest.TestCase):
    def test_resource_gate_requires_30_samples_and_all_preregistered_thresholds(self) -> None:
        module = importlib.import_module("teaching.control_plane_phase5_evidence")
        samples = [
            {"startup_ms": 120.0 + index, "rss_bytes": 80 * 1024 * 1024,
             "cpu_seconds": 0.02}
            for index in range(30)
        ]
        passed = module.evaluate_resource_samples(
            samples,
            controller_schema_bytes=5 * 1024 * 1024,
            install_delta_bytes=60 * 1024 * 1024,
            empty_databases_bytes=1024 * 1024,
            action_growth_bytes=4 * 1024 * 1024,
        )
        self.assertEqual(passed["status"], "passed")
        too_few = module.evaluate_resource_samples(
            samples[:29], controller_schema_bytes=5 * 1024 * 1024,
            install_delta_bytes=60 * 1024 * 1024,
            empty_databases_bytes=1024 * 1024,
            action_growth_bytes=4 * 1024 * 1024,
        )
        self.assertEqual(too_few["status"], "failed")
        high_rss = [dict(item, rss_bytes=151 * 1024 * 1024) for item in samples]
        killed = module.evaluate_resource_samples(
            high_rss, controller_schema_bytes=5 * 1024 * 1024,
            install_delta_bytes=60 * 1024 * 1024,
            empty_databases_bytes=1024 * 1024,
            action_growth_bytes=4 * 1024 * 1024,
        )
        self.assertEqual(killed["status"], "failed")
        self.assertIn("rss-p95", killed["failed_thresholds"])


class Phase5UpgradeTests(unittest.TestCase):
    def test_upgrade_gate_requires_old_and_new_runtime_with_one_workflow_identity(self) -> None:
        module = importlib.import_module("teaching.control_plane_phase5_upgrade")
        passed = module.evaluate_upgrade_observation(
            old_dbos_version="2.28.0", new_dbos_version="2.29.0",
            action_id="action-1", recovered_workflow_id="action-1",
            workflow_rows=1, terminal_status="completed", external_kill=True,
        )
        self.assertEqual(passed["status"], "passed")
        duplicate = module.evaluate_upgrade_observation(
            old_dbos_version="2.28.0", new_dbos_version="2.29.0",
            action_id="action-1", recovered_workflow_id="replacement",
            workflow_rows=2, terminal_status="completed", external_kill=True,
        )
        self.assertEqual(duplicate["status"], "failed")
        self.assertFalse(duplicate["checks"]["single_workflow_identity"])


class Phase5UserSupervisorTests(unittest.TestCase):
    def test_user_supervisor_requires_restart_heartbeat_and_fence_takeover(self) -> None:
        module = importlib.import_module("teaching.control_plane_phase5_supervisor")
        rows = [
            {"generation": 1, "pid": 100, "owner_id": "owner-1", "fence_epoch": 1,
             "heartbeat_recorded": True, "old_fence_rejected": None},
            {"generation": 2, "pid": 200, "owner_id": "owner-2", "fence_epoch": 2,
             "heartbeat_recorded": True, "old_fence_rejected": True},
        ]
        passed = module.evaluate_supervisor_rows(
            rows, supervisor_kind="systemd-user", cleanup_observed=True
        )
        self.assertEqual(passed["status"], "passed")
        same_pid = [dict(rows[0]), dict(rows[1], pid=100)]
        failed = module.evaluate_supervisor_rows(
            same_pid, supervisor_kind="systemd-user", cleanup_observed=True
        )
        self.assertEqual(failed["status"], "failed")
        self.assertFalse(failed["checks"]["cross_process_restart"])

    def test_task_supervisor_launches_workers_from_repository_module(self) -> None:
        module = importlib.import_module("teaching.control_plane_phase5_supervisor")
        with tempfile.TemporaryDirectory(prefix="ds-lite-phase5-supervisor-") as directory:
            root = Path(directory)
            witness = root / "witness.jsonl"
            ready = root / "ready.json"
            exit_code = module.task_supervisor(
                root / "state", witness, ready, hold_seconds=0.0
            )
            rows = module._read_rows(witness)
            self.assertEqual(exit_code, 0)
            self.assertEqual(len(rows), 2)
            self.assertNotEqual(rows[0]["pid"], rows[1]["pid"])
            self.assertTrue(ready.is_file())


class Phase5ProcessChaosTests(unittest.TestCase):
    def test_real_host_chaos_aggregate_requires_ten_per_fault_mode_and_negative_evidence(self) -> None:
        module = importlib.import_module("teaching.control_plane_phase5_evidence")
        with tempfile.TemporaryDirectory(prefix="ds-lite-phase5-chaos-aggregate-") as directory:
            root = Path(directory)
            controller = []
            app_server = []
            both = []
            for index in range(10):
                controller_path = root / f"controller-{index}.json"
                controller_path.write_text(json.dumps({
                    "sample_id": f"controller-{index}", "status": "passed", "turn_start_count": 3,
                    "checks": {"response_loss_injected": True, "response_loss_reconciled": True},
                }), encoding="utf-8")
                controller.append(controller_path)
                for name, paths in (("app", app_server), ("both", both)):
                    path = root / f"{name}-{index}.json"
                    path.write_text(json.dumps({
                        "sample_id": f"{name}-{index}", "status": "passed", "checks": {
                            "no_recovery_redispatch": True, "terminal_recovered": True,
                            "workspace_unchanged": True,
                        },
                    }), encoding="utf-8")
                    paths.append(path)
            failed = root / "failed.json"
            failed.write_text(json.dumps({"status": "failed"}), encoding="utf-8")
            result = module.aggregate_real_host_chaos(
                controller, app_server, both, [failed], output=root / "aggregate.json",
            )
            self.assertEqual(result["status"], "passed")
            self.assertTrue(result["checks"]["negative_run_preserved"])


class Phase5NetworkTests(unittest.TestCase):
    def test_disconnect_sample_requires_real_turn_failure_and_content_free_proxy(self) -> None:
        module = importlib.import_module("teaching.control_plane_phase5_network")
        proxy = {"drop_triggered": True, "content_persisted": False}
        events = {"event_type_counts": {"thread.started": 1, "turn.started": 1, "turn.failed": 1},
                  "error_classes": ["stream-disconnect"]}
        self.assertTrue(module.evaluate_disconnect_sample(proxy, events))
        self.assertFalse(module.evaluate_disconnect_sample(dict(proxy, content_persisted=True), events))

    def test_network_event_summary_redacts_error_text(self) -> None:
        module = importlib.import_module("teaching.control_plane_phase5_network")
        marker = "SECRET-NETWORK-MESSAGE"
        summary = module._event_summary([
            json.dumps({"type": "thread.started"}), json.dumps({"type": "turn.started"}),
            json.dumps({"type": "error", "message": f"429 rate limit {marker}"}),
            json.dumps({"type": "turn.failed", "error": {"message": "HTTP 503"}}),
        ])
        self.assertEqual(summary["error_classes"], ["provider-5xx", "rate-limit"])
        self.assertNotIn(marker, json.dumps(summary))

    def test_chaos_matrix_requires_exact_unique_passing_samples(self) -> None:
        module = importlib.import_module("teaching.control_plane_phase5_chaos_matrix")
        receipts = [{"sample_id": f"sample-{index}", "status": "passed"} for index in range(10)]
        self.assertEqual(module.evaluate_matrix(receipts, 10)["status"], "passed")
        receipts[-1] = {"sample_id": "sample-8", "status": "failed"}
        failed = module.evaluate_matrix(receipts, 10)
        self.assertEqual(failed["status"], "failed")
        self.assertFalse(failed["checks"]["unique_sample_identity"])
        self.assertFalse(failed["checks"]["all_samples_passed"])

    def test_process_chaos_requires_exact_resume_without_second_turn_start(self) -> None:
        module = importlib.import_module("teaching.control_plane_phase5_process_chaos")
        barrier = {"controller_pid": 1, "app_server_pid": 2, "thread_id": "t", "turn_id": "u",
                   "prekill_disposition": "active"}
        recovery = {
            "controller_pid": 3, "app_server_pid": 4, "thread_id": "t", "turn_id": "u",
            "disposition": "terminal",
        }
        passed = module.evaluate_process_chaos(
            scenario="controller-and-app-server", barrier=barrier, recovery=recovery,
            start_methods=["initialize", "thread/start", "turn/start"],
            recovery_methods=["initialize", "thread/resume"],
            killed_app_server=True, killed_controller=True, workspace_unchanged=True,
        )
        self.assertEqual(passed["status"], "passed")
        duplicate = module.evaluate_process_chaos(
            scenario="controller-and-app-server", barrier=barrier, recovery=recovery,
            start_methods=["turn/start"], recovery_methods=["thread/resume", "turn/start"],
            killed_app_server=True, killed_controller=True, workspace_unchanged=True,
        )
        self.assertEqual(duplicate["status"], "failed")

    def test_turn_status_reads_only_the_exact_turn(self) -> None:
        module = importlib.import_module("teaching.control_plane_phase5_process_chaos")
        response = {"result": {"thread": {"turns": [
            {"id": "other", "status": "completed"},
            {"id": "target", "status": "inProgress"},
        ]}}}
        self.assertEqual(module._turn_status(response, "target"), "inProgress")
        self.assertIsNone(module._turn_status(response, "missing"))


class Phase5CandidateBindingTests(unittest.TestCase):
    def test_candidate_manifest_is_stable_and_excludes_evidence_and_cache(self) -> None:
        module = importlib.import_module("ds_lite_control.candidate")
        with tempfile.TemporaryDirectory(prefix="ds-lite-phase5-candidate-") as directory:
            root = Path(directory)
            (root / "src").mkdir()
            (root / "src" / "main.py").write_text("print('ok')\n", encoding="utf-8")
            (root / "__pycache__").mkdir()
            (root / "__pycache__" / "main.pyc").write_bytes(b"cache")
            (root / ".tmp-validation-run" / "trace.json").parent.mkdir()
            (root / ".tmp-validation-run" / "trace.json").write_text("{}\n", encoding="utf-8")
            (root / "ds-lite-autoresearch-runner-example" / "state.json").parent.mkdir()
            (root / "ds-lite-autoresearch-runner-example" / "state.json").write_text("{}\n", encoding="utf-8")
            (root / "System.Management.Automation.Internal.Host.InternalHost" / "stdout.txt").parent.mkdir()
            (root / "System.Management.Automation.Internal.Host.InternalHost" / "stdout.txt").write_text("temp\n", encoding="utf-8")
            (root / "research" / ".validation-tmp" / "run").mkdir(parents=True)
            (root / "research" / ".validation-tmp" / "run" / "receipt.json").write_text(
                "{}\n", encoding="utf-8"
            )
            first = module.build_candidate_manifest(root)
            second = module.build_candidate_manifest(root)
            self.assertEqual(first["candidate_digest"], second["candidate_digest"])
            self.assertEqual([entry["path"] for entry in first["files"]], ["src/main.py"])

    def test_repository_candidate_uses_git_visible_files_and_write_once_output(self) -> None:
        module = importlib.import_module("ds_lite_control.candidate")
        with tempfile.TemporaryDirectory(prefix="ds-lite-phase5-git-candidate-") as directory:
            root = Path(directory)
            subprocess.run(["git", "init", str(root)], check=True, capture_output=True)
            (root / ".gitignore").write_text("ignored/\n", encoding="utf-8")
            (root / "tracked.txt").write_text("tracked\n", encoding="utf-8")
            (root / "research").mkdir()
            (root / "research" / "historical-receipt.json").write_text("{}\n", encoding="utf-8")
            subprocess.run(
                ["git", "-C", str(root), "add", ".gitignore", "tracked.txt",
                 "research/historical-receipt.json"],
                check=True, capture_output=True,
            )
            (root / "untracked.txt").write_text("untracked\n", encoding="utf-8")
            (root / ".tmp-run" / "receipt.json").parent.mkdir()
            (root / ".tmp-run" / "receipt.json").write_text("{}\n", encoding="utf-8")
            (root / "ds-lite-autoresearch-runner-fixture" / "state.json").parent.mkdir()
            (root / "ds-lite-autoresearch-runner-fixture" / "state.json").write_text("{}\n", encoding="utf-8")
            (root / "ignored").mkdir()
            (root / "ignored" / "evidence.bin").write_bytes(b"ignored")
            manifest = module.build_repository_candidate_manifest(root)
            self.assertEqual(
                [entry["path"] for entry in manifest["files"]],
                [".gitignore", "tracked.txt", "untracked.txt"],
            )
            output = root / "research" / ".validation-tmp" / "candidate-manifest.json"
            module.write_candidate_manifest(output, manifest)
            with self.assertRaises(FileExistsError):
                module.write_candidate_manifest(output, manifest)

    def test_release_candidate_digest_binds_source_and_platform_packages(self) -> None:
        module = importlib.import_module("ds_lite_control.candidate")
        source = {"schema_version": "ds-lite.candidate-manifest.v1", "candidate_digest": "a" * 64}
        packages = {
            "windows-x86_64": {
                "schema_version": "ds-lite.candidate-manifest.v1",
                "candidate_digest": "b" * 64,
            },
            "linux-x86_64": {
                "schema_version": "ds-lite.candidate-manifest.v1",
                "candidate_digest": "c" * 64,
            },
        }
        first = module.bind_release_candidate(source, packages)
        second = module.bind_release_candidate(source, dict(reversed(list(packages.items()))))
        self.assertEqual(first, second)
        self.assertEqual(first["source_digest"], "a" * 64)
        self.assertEqual(len(first["candidate_digest"]), 64)

    def test_phase5_aggregate_fails_closed_on_missing_or_drifting_candidate(self) -> None:
        module = importlib.import_module("ds_lite_control.candidate")
        expected = "a" * 64
        gate_receipts = [
            {"gate_id": "phase4-real-gate", "status": "passed", "candidate_digest": expected},
            {"gate_id": "phase5-real-host", "status": "passed", "candidate_digest": expected},
        ]
        allowed = module.aggregate_candidate_bound_gates(
            expected, ["phase4-real-gate", "phase5-real-host"], gate_receipts
        )
        self.assertTrue(allowed["release_allowed"])
        missing = module.aggregate_candidate_bound_gates(
            expected, ["phase4-real-gate", "phase5-real-host"], gate_receipts[:1]
        )
        self.assertFalse(missing["release_allowed"])
        self.assertEqual(missing["missing_gates"], ["phase5-real-host"])
        drifted_receipts = [dict(gate_receipts[0]), dict(gate_receipts[1])]
        drifted_receipts[1]["candidate_digest"] = "b" * 64
        drifted = module.aggregate_candidate_bound_gates(
            expected, ["phase4-real-gate", "phase5-real-host"], drifted_receipts
        )
        self.assertFalse(drifted["release_allowed"])
        self.assertEqual(drifted["candidate_mismatch_gates"], ["phase5-real-host"])

    def test_complete_profile_candidate_binding_is_strict_but_opt_in(self) -> None:
        expected = "a" * 64
        with tempfile.TemporaryDirectory(prefix="ds-lite-phase5-complete-") as directory:
            root = Path(directory)
            values = []
            for gate, schema in COMPLETE_GATE_SCHEMAS.items():
                path = root / f"{gate}.json"
                payload = {
                    "schema_version": schema,
                    "status": "passed",
                    "candidate_digest": expected,
                }
                if gate == "hook_in_turn_repair":
                    payload.update({
                        "deterministic_verifier": True,
                        "release_evidence": True,
                        "verified_turn_id": "turn-1",
                    })
                path.write_text(json.dumps(payload), encoding="utf-8")
                values.append(f"{gate}={path}")
            allowed, code = evaluate(
                values, SCHEMA_V2, COMPLETE_PROFILE, candidate_digest=expected
            )
            self.assertEqual(code, 0)
            self.assertTrue(allowed["release_allowed"])
            drifted = json.loads((root / "wsl.json").read_text(encoding="utf-8"))
            drifted["candidate_digest"] = "b" * 64
            (root / "wsl.json").write_text(json.dumps(drifted), encoding="utf-8")
            blocked, code = evaluate(
                values, SCHEMA_V2, COMPLETE_PROFILE, candidate_digest=expected
            )
            self.assertEqual(code, 2)
            self.assertFalse(blocked["release_allowed"])
            self.assertEqual(blocked["candidate_mismatch_gates"], ["wsl"])


class Phase5ControlAggregateTests(unittest.TestCase):
    def test_control_aggregate_reads_candidate_digest_from_indexed_gate_receipt(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ds-lite-phase5-control-aggregate-") as directory:
            root = Path(directory)
            store = ControlStore(root / "control.sqlite3")
            try:
                epoch = store.create_job_work_item("job-1", "phase5-real-host", "owner-1")
                artifacts = root / "artifacts"
                artifacts.mkdir()
                (artifacts / "result.json").write_text(
                    json.dumps({"schema_version": "fixture.v1", "measurement": 42}),
                    encoding="utf-8",
                )
                policy = {
                    "schema_version": "ds-lite.gate-policy.v1",
                    "policy_id": "phase5-policy-v1",
                    "minimum_evidence_class": "offline",
                    "required_artifacts": [{
                        "path": "result.json", "schema_version": "fixture.v1",
                        "required_fields": {"measurement": 42},
                    }],
                }
                manifest = EvidenceManager(
                    store, root / "evidence", root / "private-spool"
                ).freeze(
                    "job-1", "phase5-real-host", artifacts, policy,
                    evidence_class="offline", owner_id="owner-1", fence_epoch=epoch,
                )
                verifier = DeterministicVerifier(store, root / "receipts").verify(
                    "phase5-real-host", manifest["evidence_set_id"], policy,
                    owner_id="owner-1", fence_epoch=epoch,
                )
                reviews = ReviewCoordinator(store, root / "receipts")
                request = reviews.prepare(
                    "phase5-real-host", manifest["evidence_set_id"], verifier["verifier_id"],
                    schema_digest="s" * 64, model="gpt-5.6-sol",
                    owner_id="owner-1", fence_epoch=epoch,
                )
                reviews.bind_thread(
                    request["review_id"], "review-thread", worker_thread_ids=set(),
                    owner_id="owner-1", fence_epoch=epoch,
                )
                reviews.record_result(
                    request["review_id"], {
                        "schema_version": "ds-lite.review-sidecar.v1", "verdict": "accept",
                        "finding_codes": [], "evidence_refs": ["result.json"],
                    },
                    post_manifest_hash=manifest["manifest_hash"], reviewer_turn_id="review-turn",
                    owner_id="owner-1", fence_epoch=epoch,
                )
                candidate_digest = "a" * 64
                GateDecisionEngine(store, root / "receipts").decide(
                    "phase5-real-host", manifest["evidence_set_id"], request["review_id"],
                    owner_id="owner-1", fence_epoch=epoch,
                    candidate_digest=candidate_digest,
                )
                aggregate = StrictReleaseAggregate(store, root / "receipts")
                allowed = aggregate.decide("job-1", {
                    "schema_version": "ds-lite.release-profile.v1",
                    "profile_id": "phase5", "required_gates": ["phase5-real-host"],
                    "fixture_only": False, "candidate_digest": candidate_digest,
                })
                self.assertTrue(allowed["release_allowed"])
                drifted = aggregate.decide("job-1", {
                    "schema_version": "ds-lite.release-profile.v1",
                    "profile_id": "phase5-drift", "required_gates": ["phase5-real-host"],
                    "fixture_only": False, "candidate_digest": "b" * 64,
                })
                self.assertFalse(drifted["release_allowed"])
                self.assertEqual(drifted["candidate_mismatch_gates"], ["phase5-real-host"])
            finally:
                store.close()


if __name__ == "__main__":
    unittest.main()
