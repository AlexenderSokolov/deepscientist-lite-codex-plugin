from __future__ import annotations

import hashlib
import importlib.util
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "validation" / "acquire_pinned_codex.py"
SPEC = importlib.util.spec_from_file_location("acquire_pinned_codex", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class CodexPinTests(unittest.TestCase):
    def test_integrity_helpers_are_deterministic(self) -> None:
        root = Path(tempfile.mkdtemp(prefix="ds-lite-codex-pin-"))
        path = root / "sample.bin"
        path.write_bytes(b"codex-pin")
        self.assertEqual(MODULE._sha256(path), hashlib.sha256(b"codex-pin").hexdigest().upper())
        self.assertTrue(MODULE._sha512_integrity(path))

    def test_expected_pin_is_explicit_and_not_empty(self) -> None:
        self.assertEqual(MODULE.EXPECTED_VERSION, "0.144.5")
        self.assertEqual(len(MODULE.EXPECTED_BINARY_SHA256), 64)
        self.assertEqual(len(MODULE.EXPECTED_PACKAGES), 2)
