import argparse
import json
import tempfile
import unittest
from pathlib import Path

from teaching.dbos_sqlite_recovery_probe import _dbos_version, _parse_child_event, _sqlite_url, _write_once


class DBOSSQLiteRecoveryProbeTests(unittest.TestCase):
    def test_sqlite_url_uses_resolved_forward_slash_path(self):
        with tempfile.TemporaryDirectory() as directory:
            url = _sqlite_url(Path(directory) / "runtime.sqlite3")
            self.assertTrue(url.startswith("sqlite:///"))
            self.assertIn("runtime.sqlite3", url)
            self.assertNotIn("\\", url)

    def test_parses_only_named_json_child_event(self):
        output = "library log\n" + json.dumps({"event": "recovered", "fence_result": "rejected"}) + "\n"
        event = _parse_child_event(output, "recovered")
        self.assertEqual(event["fence_result"], "rejected")
        self.assertIsNone(_parse_child_event(output, "submitted"))

    def test_write_once_refuses_existing_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "receipt.json"
            _write_once(path, {"status": "blocked"})
            with self.assertRaises(FileExistsError):
                _write_once(path, {"status": "passed"})

    def test_reads_pinned_dependency_directory_version(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "dbos-2.29.0.dist-info").mkdir()
            self.assertEqual(_dbos_version(root), "2.29.0")


if __name__ == "__main__":
    unittest.main()
