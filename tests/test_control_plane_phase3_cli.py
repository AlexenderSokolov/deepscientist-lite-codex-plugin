from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTROLLER_ROOT = ROOT / "plugins" / "deepscientist-lite-core" / "controller"
sys.path.insert(0, str(CONTROLLER_ROOT))

from ds_lite_control.cli import build_parser, doctor_report, main
from ds_lite_control.failure_policy import FailureClassifier
from ds_lite_control.scheduler import DagScheduler
from ds_lite_control.store import ControlStore


class Phase3CliTests(unittest.TestCase):
    def test_doctor_requires_schema_v3(self) -> None:
        current = doctor_report(
            python_version="3.13.5", dbos_version="2.29.0", schema_version=4,
            integrity="ok",
            codex_schema_digest="9e22b7c4174cdaa87fc3240bce6bfecf8855f263eddfed3e97e49cb165527afb",
        )
        old = doctor_report(
            python_version="3.13.5", dbos_version="2.29.0", schema_version=2,
            integrity="ok",
            codex_schema_digest="9e22b7c4174cdaa87fc3240bce6bfecf8855f263eddfed3e97e49cb165527afb",
        )
        self.assertTrue(current["managed_allowed"])
        self.assertFalse(old["managed_allowed"])

    def test_supervisor_commands_and_control_serve_are_stable(self) -> None:
        parser = build_parser()
        for argv, command in (
            (["supervisor", "run", "--project", ".", "--job-id", "job-1"], "run"),
            (["supervisor", "status", "--project", "."], "status"),
            (["supervisor", "stop", "--project", "."], "stop"),
            (["supervisor", "render", "--project", ".", "--platform", "windows", "--output", "task.xml"], "render"),
            (["control", "serve", "job-1", "--project", ".", "--once"], "serve"),
        ):
            with self.subTest(command=command):
                parsed = parser.parse_args(argv)
                self.assertEqual(
                    getattr(parsed, "supervisor_command", None)
                    or getattr(parsed, "control_command", None),
                    command,
                )

    def test_broker_ambient_home_is_explicit_opt_in(self) -> None:
        parsed = build_parser().parse_args([
            "broker", "serve", "--codex-bin", "codex.exe", "--home", "unused-home",
            "--schema-root", "schema", "--journal", "journal.jsonl",
            "--ready-file", "ready.json", "--ambient-home",
        ])
        self.assertTrue(parsed.ambient_home)

    def test_control_status_json_projects_all_gates(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ds-lite-phase3-cli-") as directory:
            project = Path(directory)
            control_root = project / ".ds-lite"
            store = ControlStore(control_root / "control.sqlite3")
            try:
                scheduler = DagScheduler(store, FailureClassifier(seed=1))
                scheduler.register_job(
                    "job-1",
                    [{"id": "a", "type": "analysis"}, {"id": "b", "type": "analysis"}],
                    [],
                )
                scheduler.claim_ready("job-1", "owner-1")
                store.record_supervisor_heartbeat(
                    "ds-lite-supervisor", "owner-1", controller_pid=123,
                    witness_hash="a" * 64,
                )
            finally:
                store.close()
            output = io.StringIO()
            with redirect_stdout(output):
                code = main([
                    "control", "status", "job-1", "--project", str(project), "--json"
                ])
            payload = json.loads(output.getvalue())
            self.assertEqual(code, 0)
            self.assertEqual(payload["schema_version"], "ds-lite.project-status.v3")
            self.assertEqual([gate["work_item_id"] for gate in payload["gates"]], ["a", "b"])
            self.assertFalse(payload["release_allowed"])


if __name__ == "__main__":
    unittest.main()
