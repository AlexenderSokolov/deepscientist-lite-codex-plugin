from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from teaching import formal_cache_acceptance as module


class FormalCacheAcceptanceTests(unittest.TestCase):
    def test_live_acceptance_requires_stable_runtime_and_schema_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            binary = root / "codex.exe"
            binary.write_bytes(b"codex")
            schema_root = root / "schemas"
            schema_root.mkdir()
            expected_sha = module._sha256(binary)

            def fake_run(command, env, cwd):
                if command[-3:] == ["plugin", "list", "--json"]:
                    listed = [{"name": name, "version": version}
                              for name, version in module.EXPECTED_PACKAGES.items()]
                    return 0, 1, "d" * 64, listed
                return 0, 1, "e" * 64, None

            runtime = {
                "valid": True, "expected_codex_version": "0.146.0",
                "codex_binary_version": "0.146.0",
                "schema": {"valid": True, "manifest_digest": "f" * 64,
                           "observed_bundle_digest": "a" * 64},
            }
            with patch.object(module, "verify_runtime_selection", return_value=runtime), \
                    patch.object(module, "_run", side_effect=fake_run):
                receipt = module.run(
                    codex_bin=binary, repo_root=root, output_root=root / "out",
                    schema_root=schema_root, expected_version="0.146.0",
                    expected_sha256=expected_sha, candidate_digest="a" * 64,
                )
            self.assertEqual(receipt["status"], "passed")
            self.assertEqual(receipt["cli_identity"]["observed_version"], "0.146.0")
            self.assertTrue(receipt["schema_identity"]["valid"])
            self.assertEqual(receipt["cli_identity"]["sha256"], expected_sha.lower())
            self.assertEqual(receipt["candidate_digest"], "a" * 64)

    def test_nonstable_version_or_invalid_schema_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            binary = root / "codex.exe"
            binary.write_bytes(b"codex")
            schemas = root / "schemas"
            schemas.mkdir()
            with self.assertRaisesRegex(module.FormalCacheError, "stable 0.146.0"):
                module.run(
                    codex_bin=binary, repo_root=root, output_root=root / "old",
                    schema_root=schemas, expected_version="0.144.5",
                    expected_sha256=module._sha256(binary), candidate_digest="a" * 64,
                )
            runtime = {
                "valid": False, "expected_codex_version": "0.146.0",
                "codex_binary_version": "0.146.0", "schema": {"valid": False},
            }
            with patch.object(module, "verify_runtime_selection", return_value=runtime):
                with self.assertRaisesRegex(module.FormalCacheError, "runtime or schema"):
                    module.run(
                        codex_bin=binary, repo_root=root, output_root=root / "invalid",
                        schema_root=schemas, expected_version="0.146.0",
                        expected_sha256=module._sha256(binary), candidate_digest="a" * 64,
                    )

    def test_live_acceptance_rejects_an_invalid_candidate_digest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            binary = root / "codex.exe"
            binary.write_bytes(b"codex")
            schemas = root / "schemas"
            schemas.mkdir()
            with self.assertRaisesRegex(module.FormalCacheError, "candidate digest"):
                module.run(
                    codex_bin=binary, repo_root=root, output_root=root / "out",
                    schema_root=schemas, expected_version="0.146.0",
                    expected_sha256=module._sha256(binary), candidate_digest="not-a-digest",
                )

    def test_legacy_v1_receipt_remains_parseable(self) -> None:
        legacy = {
            "schema_version": "ds-lite.formal-cache-acceptance.v1",
            "status": "passed",
            "cli_identity": {"version": "0.144.5", "sha256_match": True},
            "model_request_made": False,
        }
        normalized = module.validate_receipt(legacy)
        self.assertEqual(normalized["observed_version"], "0.144.5")
        self.assertEqual(normalized["receipt_generation"], "legacy")
        with self.assertRaisesRegex(module.FormalCacheError, "schema"):
            module.validate_receipt({**legacy, "schema_version": "unknown"})


if __name__ == "__main__":
    unittest.main()
