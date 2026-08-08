from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.validation.package_identity import tree_digest
from tools.validation.package_identity_receipt import build_identity


class PackageIdentityReceiptTests(unittest.TestCase):
    def test_tree_digest_accepts_a_relative_root(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "artifact.txt").write_text("identity\n", encoding="utf-8")
            previous = Path.cwd()
            try:
                import os
                os.chdir(root.parent)
                self.assertEqual(tree_digest(Path(root.name)), tree_digest(root))
            finally:
                os.chdir(previous)

    def test_tree_digest_excludes_repository_and_temporary_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "plugin.json").write_text("{}", encoding="utf-8")
            baseline = tree_digest(root)
            (root / ".git").mkdir()
            (root / ".git" / "index").write_text("index", encoding="utf-8")
            (root / "research" / ".validation-tmp").mkdir(parents=True)
            (root / "research" / ".validation-tmp" / "receipt.json").write_text("{}", encoding="utf-8")
            (root / ".tmp-validation" / "trace.json").parent.mkdir()
            (root / ".tmp-validation" / "trace.json").write_text("{}", encoding="utf-8")
            self.assertEqual(tree_digest(root), baseline)

    def test_release_candidate_and_receipts_bind_distinct_states(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            source = root / "source"
            source.mkdir()
            (source / "plugin.json").write_text("{}", encoding="utf-8")
            candidate_receipt = root / "release-candidate.json"
            candidate_receipt.write_text(json.dumps({
                "schema_version": "ds-lite.phase5-release-candidate.v1",
                "candidate_digest": "a" * 64,
            }), encoding="utf-8")
            cache = root / "cache"
            cache.mkdir()
            (cache / "loaded.json").write_text("{}", encoding="utf-8")
            cache_receipt = root / "formal-cache.json"
            cache_receipt.write_text(json.dumps({
                "schema_version": "ds-lite.formal-cache-acceptance.v1",
                "candidate_digest": "a" * 64,
                "status": "passed",
            }), encoding="utf-8")
            host_receipt = root / "host.json"
            host_receipt.write_text(json.dumps({"status": "blocked"}), encoding="utf-8")
            identity = build_identity(
                source=source,
                candidate_receipt=candidate_receipt,
                cache=cache,
                cache_receipt=cache_receipt,
                host_receipt=host_receipt,
                loaded_runtime="codex-cli-0.146.0",
                tag="v0.10.0-beta.2",
            )
            self.assertEqual(identity["candidate_digest"], "a" * 64)
            self.assertEqual(identity["status"]["candidate"], "observed")
            self.assertEqual(identity["status"]["host"], "not-verified")
            self.assertEqual(identity["host_status"], "blocked")
            self.assertEqual(len(identity["cache_digest"]), 64)
            self.assertEqual(len(identity["cache_receipt_sha256"]), 64)
            self.assertFalse(identity["release_allowed"])


if __name__ == "__main__":
    unittest.main()
