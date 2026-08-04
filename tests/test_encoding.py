#!/usr/bin/env python3
"""Encoding tests for DS Lite v6.

Tests UTF-8 BOM handling, Chinese filename handling, JSON encoding
consistency, and cross-platform output encoding.
"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


class UTF8BOMHandlingTests(unittest.TestCase):
    """Test UTF-8 BOM detection and handling."""

    def test_json_without_bom_passes(self):
        """A JSON file without BOM should be detected as clean."""
        with tempfile.TemporaryDirectory() as tmpdir:
            f = Path(tmpdir) / "test.json"
            f.write_bytes(b'{"key": "value"}')
            first_bytes = f.read_bytes()[:3]
            self.assertNotEqual(first_bytes, b"\xef\xbb\xbf")

    def test_json_with_bom_detected(self):
        """A JSON file with BOM should be detected."""
        with tempfile.TemporaryDirectory() as tmpdir:
            f = Path(tmpdir) / "test.json"
            f.write_bytes(b"\xef\xbb\xbf" + b'{"key": "value"}')
            first_bytes = f.read_bytes()[:3]
            self.assertEqual(first_bytes, b"\xef\xbb\xbf")

    def test_repo_json_files_no_bom(self):
        """All tracked JSON files should not have UTF-8 BOM."""
        skip_dirs = {".git", "__pycache__", ".tmp-test-artifacts", ".pytest_cache",
                     "node_modules", ".validation-tmp", ".validation-tmp-resume-02"}
        json_files = []
        for root, dirs, files in os.walk(str(REPO_ROOT)):
            dirs[:] = [d for d in dirs if d not in skip_dirs and not d.startswith(".tmp")]
            for f in files:
                if f.endswith(".json"):
                    json_files.append(Path(root) / f)

        self.assertGreater(len(json_files), 0, "No JSON files found in repo")
        bom_files = []
        for jf in json_files:
            with open(jf, "rb") as f:
                first_bytes = f.read(3)
            if first_bytes == b"\xef\xbb\xbf":
                bom_files.append(str(jf))
        self.assertEqual(bom_files, [], f"JSON files with BOM: {bom_files}")


class ChineseFilenameHandlingTests(unittest.TestCase):
    """Test handling of Chinese characters in filenames."""

    def test_chinese_filename_create_read(self):
        """Chinese filenames should be creatable and readable."""
        with tempfile.TemporaryDirectory() as tmpdir:
            chinese_name = "\u4e2d\u6587\u6587\u4ef6.json"
            f = Path(tmpdir) / chinese_name
            f.write_text('{"test": true}', encoding="utf-8")
            self.assertTrue(f.exists())
            data = json.loads(f.read_text(encoding="utf-8"))
            self.assertTrue(data["test"])

    def test_chinese_content_in_json(self):
        """Chinese content should survive JSON round-trip."""
        original = {"title": "\u4e2d\u6587\u6807\u9898", "body": "\u8fd9\u662f\u4e00\u4e2a\u6d4b\u8bd5"}
        json_str = json.dumps(original, ensure_ascii=False)
        parsed = json.loads(json_str)
        self.assertEqual(parsed["title"], original["title"])
        self.assertEqual(parsed["body"], original["body"])


class JSONEncodingConsistencyTests(unittest.TestCase):
    """Test that JSON files are consistently encoded."""

    def test_all_json_files_valid_utf8(self):
        """All JSON files should be readable as UTF-8."""
        skip_dirs = {".git", "__pycache__", ".tmp-test-artifacts", ".pytest_cache",
                     "node_modules", ".validation-tmp", ".validation-tmp-resume-02"}
        json_files = []
        for root, dirs, files in os.walk(str(REPO_ROOT)):
            dirs[:] = [d for d in dirs if d not in skip_dirs and not d.startswith(".tmp")]
            for f in files:
                if f.endswith(".json"):
                    json_files.append(Path(root) / f)

        for jf in json_files:
            try:
                jf.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                self.fail(f"JSON file {jf} is not valid UTF-8")


class CrossPlatformOutputEncodingTests(unittest.TestCase):
    """Test output encoding on different platforms."""

    def test_stdout_encoding_is_set(self):
        """stdout encoding should be set."""
        enc = sys.stdout.encoding or ""
        self.assertTrue(len(enc) > 0, f"stdout encoding is empty: {enc}")

    def test_python_files_are_valid_utf8(self):
        """All Python files in Core should be valid UTF-8."""
        py_files = list((REPO_ROOT / "plugins" / "deepscientist-lite-core" / "scripts").glob("*.py"))
        self.assertGreater(len(py_files), 10)
        for pf in py_files:
            content = pf.read_text(encoding="utf-8")
            self.assertIsInstance(content, str)


if __name__ == "__main__":
    unittest.main()
