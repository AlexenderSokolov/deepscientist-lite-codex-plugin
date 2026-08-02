import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTROLLER_ROOT = ROOT / "plugins" / "deepscientist-lite-core" / "controller"
sys.path.insert(0, str(CONTROLLER_ROOT))

from ds_lite_control.backup import backup_control_plane, restore_control_plane
from ds_lite_control.cli import doctor_report
from ds_lite_control.dbos_bridge import PHASE1_WORKFLOW_NAMES, sqlite_url
from ds_lite_control.domain import ControlStore


class Phase1CliContracts(unittest.TestCase):
    def test_doctor_allows_only_verified_controller_runtime(self):
        allowed = doctor_report(
            python_version="3.13.5", dbos_version="2.29.0", schema_version=4,
            integrity="ok", codex_schema_digest="9e22b7c4174cdaa87fc3240bce6bfecf8855f263eddfed3e97e49cb165527afb",
        )
        blocked = doctor_report(
            python_version="3.14.4", dbos_version="2.29.0", schema_version=1,
            integrity="ok", codex_schema_digest="9e22b7c4174cdaa87fc3240bce6bfecf8855f263eddfed3e97e49cb165527afb",
        )
        self.assertTrue(allowed["managed_allowed"])
        self.assertFalse(blocked["managed_allowed"])
        self.assertFalse(allowed["release_allowed"])
        self.assertEqual(allowed["plugin_hooks_default"], "disabled")

    def test_doctor_blocks_schema_v2_without_protocol_journal(self):
        blocked = doctor_report(
            python_version="3.13.5", dbos_version="2.29.0", schema_version=4,
            integrity="ok", codex_schema_digest="9e22b7c4174cdaa87fc3240bce6bfecf8855f263eddfed3e97e49cb165527afb",
            protocol_present=False,
        )
        self.assertFalse(blocked["managed_allowed"])
        self.assertFalse(blocked["checks"]["protocol_journal"])

    def test_sqlite_runtime_url_is_absolute_and_workflows_are_versioned(self):
        with tempfile.TemporaryDirectory() as directory:
            url = sqlite_url(Path(directory) / "runtime.sqlite3")
            self.assertTrue(url.startswith("sqlite:///"))
            self.assertNotIn("\\", url)
        self.assertEqual(
            set(PHASE1_WORKFLOW_NAMES),
            {"reconcile_job_v1", "run_action_v1", "project_status_v1"},
        )

    def test_restore_requires_new_destination_and_all_three_backup_parts(self):
        with tempfile.TemporaryDirectory(prefix="ds-lite-restore-") as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            store = ControlStore(source / "control.sqlite3")
            store.close()
            sqlite3.connect(source / "runtime.sqlite3").close()
            (source / "receipts").mkdir()
            (source / "receipts" / "one.json").write_text("{}\n", encoding="utf-8")
            backup = root / "backup"
            backup_control_plane(source, backup)
            restored = restore_control_plane(backup, root / "restored")
            self.assertTrue(restored["valid"])
            restored_store = ControlStore(root / "restored" / "control.sqlite3")
            try:
                self.assertEqual(restored_store.integrity_check(), "ok")
            finally:
                restored_store.close()
            with self.assertRaises(FileExistsError):
                restore_control_plane(backup, root / "restored")
            manifest_path = backup / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["files"].pop("runtime.sqlite3")
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaises(ValueError):
                restore_control_plane(backup, root / "restored-2")


if __name__ == "__main__":
    unittest.main()
