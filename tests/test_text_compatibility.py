import json
import os
import tempfile
import unittest
from pathlib import Path

from tools.validation import check_text_compatibility as checker


class TextCompatibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        base = Path(os.environ.get("TEMP", Path(__file__).resolve().parents[1] / ".validation-tmp"))
        base.mkdir(parents=True, exist_ok=True)
        cls._temp_base = base

    def temp_root(self):
        try:
            return tempfile.TemporaryDirectory(dir=self._temp_base)
        except (FileNotFoundError, PermissionError) as exc:
            self.skipTest(f"writable validation temp unavailable: {exc}")

    def make_file(self, root, name, data):
        path = Path(root) / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def test_ascii_shell_and_utf8_sources(self):
        with self.temp_root() as root:
            self.assertEqual(checker.check_file(self.make_file(root, "run.ps1", b"Write-Output ok\n"))["status"], "passed")
            result = checker.check_file(self.make_file(root, "notes.md", "中文\n".encode("utf-8")))
            self.assertTrue(result["utf8_valid"])

    def test_non_ascii_shell_bom_nul_and_replacement(self):
        with self.temp_root() as root:
            result = checker.check_file(self.make_file(root, "run.sh", "#!/bin/sh\n# 中文\n".encode("utf-8")))
            self.assertIn("non-ascii-executable", result["violations"])
            result = checker.check_file(self.make_file(root, "bom.cmd", b"\xef\xbb\xbfecho ok\n"))
            self.assertIn("bom-on-executable", result["violations"])
            result = checker.check_file(self.make_file(root, "bad.py", b"x=1\x00\n"))
            self.assertIn("nul-byte", result["violations"])
            result = checker.check_file(self.make_file(root, "replacement.md", bytes.fromhex("efbfbd")))
            self.assertIn("replacement-character", result["violations"])

    def test_mixed_and_crlf_shell_line_endings(self):
        with self.temp_root() as root:
            mixed = checker.check_file(self.make_file(root, "mixed.py", b"a\r\nb\nc\r"))
            self.assertIn("mixed-line-endings", mixed["violations"])
            shell = checker.check_file(self.make_file(root, "run.sh", b"#!/bin/sh\r\necho ok\r\n"))
            self.assertIn("crlf-shell", shell["violations"])

    def test_json_and_toml_parse(self):
        with self.temp_root() as root:
            self.assertEqual(checker.check_file(self.make_file(root, "x.json", b'{"ok": true}\n'))["parse_status"], "passed")
            self.assertEqual(checker.check_file(self.make_file(root, "x.toml", b"name = 'ok'\n"))["parse_status"], "passed")
            self.assertEqual(checker.check_file(self.make_file(root, "x.json", b"{bad}\n"))["status"], "failed")

    def test_scan_and_serializable_report(self):
        with self.temp_root() as root:
            report = checker.scan_tree(root)
            json.dumps(report)
            self.assertEqual(report["schema_version"], "ds-lite.text-compatibility.v1")

    def test_binary_assets_are_not_misclassified_as_text(self):
        with self.temp_root() as root:
            result = checker.check_file(self.make_file(root, "figure.png", b"\x89PNG\r\n\x1a\n\x00\xff"))
            self.assertEqual(result["status"], "passed")
            self.assertFalse(result["violations"])


if __name__ == "__main__":
    unittest.main()
