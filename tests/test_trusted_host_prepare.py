import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from teaching import trusted_host_prepare


class TrustedHostPrepareTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        base = Path(os.environ.get("TEMP", "."))
        try:
            base.mkdir(parents=True, exist_ok=True)
            probe = base / "ds-lite-test-write-probe"
            probe.write_text("ok", encoding="ascii")
            probe.unlink()
        except OSError as exc:
            raise unittest.SkipTest(f"writable validation temp unavailable: {exc}")

    def _source(self, root: Path) -> Path:
        source = root / "source"
        source.mkdir()
        (source / "catalog.json").write_text("{}", encoding="utf-8")
        (source / "config.toml").write_text(
            'model_provider = "custom"\nmodel_catalog_json = "catalog.json"\n\n'
            '[model_providers.custom]\nname = "custom"\nbase_url = "https://example.invalid/v1"\n'
            'wire_api = "responses"\nrequires_openai_auth = true\nenv_key = "OPENAI_API_KEY"\n',
            encoding="utf-8")
        return source

    def test_prepare_writes_valid_redacted_receipt(self):
        with tempfile.TemporaryDirectory(dir=os.environ.get("TEMP")) as directory:
            root = Path(directory)
            binary = root / "codex.exe"
            binary.write_bytes(b"pinned")
            with patch.object(trusted_host_prepare, "_sha256", return_value=trusted_host_prepare.EXPECTED_SHA256):
                receipt = trusted_host_prepare.prepare(codex_bin=binary, source_home=self._source(root), repo_root=root, pilot_root=root / "pilot", install=False)
            self.assertEqual(receipt["status"], "prepared")
            self.assertFalse(receipt["raw_output_persisted"])
            self.assertTrue(receipt["workspace_trust_configured"])
            parsed = json.loads((root / "pilot" / "preparation.json").read_text(encoding="utf-8"))
            self.assertEqual(parsed["retries"]["request_max_retries"], 0)
            self.assertNotIn("https://", json.dumps(parsed))
            config = (root / "pilot" / "codex-home" / "config.toml").read_text(encoding="utf-8")
            workspace_key = trusted_host_prepare._canonical_workspace_key(root / "pilot" / "workspace")
            self.assertIn(f"[projects.{json.dumps(workspace_key)}]", config)
            self.assertIn('trust_level = "trusted"', config)

    def test_prepare_accepts_an_explicit_stable_runtime_pin(self):
        with tempfile.TemporaryDirectory(dir=os.environ.get("TEMP")) as directory:
            root = Path(directory)
            binary = root / "codex.exe"
            binary.write_bytes(b"stable")
            stable_hash = "B" * 64
            with patch.object(trusted_host_prepare, "_sha256", return_value=stable_hash):
                receipt = trusted_host_prepare.prepare(
                    codex_bin=binary,
                    source_home=self._source(root),
                    repo_root=root,
                    pilot_root=root / "stable-pilot",
                    install=False,
                    expected_version="0.146.0",
                    expected_sha256=stable_hash,
                )
            self.assertEqual(receipt["codex_version"], "0.146.0")
            self.assertEqual(receipt["codex_sha256"], stable_hash)

    def test_existing_root_is_not_overwritten(self):
        with tempfile.TemporaryDirectory(dir=os.environ.get("TEMP")) as directory:
            root = Path(directory)
            binary = root / "codex.exe"; binary.write_bytes(b"pinned")
            source = self._source(root); pilot = root / "pilot"; pilot.mkdir(); marker = pilot / "marker"; marker.write_text("keep")
            with patch.object(trusted_host_prepare, "_sha256", return_value=trusted_host_prepare.EXPECTED_SHA256):
                with self.assertRaises(trusted_host_prepare.PreparationError):
                    trusted_host_prepare.prepare(codex_bin=binary, source_home=source, repo_root=root, pilot_root=pilot, install=False)
            self.assertEqual(marker.read_text(), "keep")

    def test_prepare_allows_a_complete_route_without_a_catalog(self):
        with tempfile.TemporaryDirectory(dir=os.environ.get("TEMP")) as directory:
            root = Path(directory)
            binary = root / "codex.exe"; binary.write_bytes(b"pinned")
            source = self._source(root)
            config = source / "config.toml"
            config.write_text(
                config.read_text(encoding="utf-8").replace('model_catalog_json = "catalog.json"\n', ""),
                encoding="utf-8",
            )
            with patch.object(trusted_host_prepare, "_sha256", return_value=trusted_host_prepare.EXPECTED_SHA256):
                receipt = trusted_host_prepare.prepare(
                    codex_bin=binary,
                    source_home=source,
                    repo_root=root,
                    pilot_root=root / "pilot-no-catalog",
                    install=False,
                )
            self.assertEqual(receipt["status"], "prepared")

    def test_formal_trusted_host_clis_run_without_pythonpath_bootstrap(self):
        repo_root = Path(__file__).resolve().parents[1]
        env = os.environ.copy()
        env.pop("PYTHONPATH", None)
        for relative in (
            "teaching/trusted_host_prepare.py",
            "teaching/trusted_hook_run.py",
        ):
            completed = subprocess.run(
                [sys.executable, relative, "--help"],
                cwd=repo_root,
                env=env,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=15,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, relative)
            self.assertIn("usage:", completed.stdout.lower(), relative)

    def test_split_core_identity_records_version_skills_hooks_and_digest(self):
        repo_root = Path(__file__).resolve().parents[1]
        identity = trusted_host_prepare._candidate_identity(repo_root)
        self.assertEqual(identity["plugin"], "deepscientist-lite")
        self.assertEqual(identity["version"], "0.9.0-beta.1")
        self.assertEqual(identity["skill_count"], 9)
        self.assertEqual(
            identity["hook_events"],
            ["PostToolUse", "PreToolUse", "Stop", "UserPromptSubmit"],
        )
        self.assertEqual(len(identity["source_sha256"]), 64)

    def test_split_core_identity_ignores_runtime_bytecode_caches(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            core = root / "plugins" / "deepscientist-lite-core"
            (core / ".codex-plugin").mkdir(parents=True)
            (core / "hooks").mkdir()
            (core / "skills" / "example").mkdir(parents=True)
            (core / "scripts").mkdir()
            (core / ".codex-plugin" / "plugin.json").write_text(
                json.dumps({"name": "deepscientist-lite", "version": "0.9.0-beta.1"}),
                encoding="utf-8",
            )
            (core / "hooks" / "hooks.json").write_text(
                json.dumps({"hooks": {"Stop": []}}), encoding="utf-8",
            )
            (core / "skills" / "example" / "SKILL.md").write_text("test", encoding="utf-8")
            (core / "scripts" / "worker.py").write_text("VALUE = 1\n", encoding="utf-8")
            before = trusted_host_prepare._candidate_identity(root)["source_sha256"]
            cache = core / "scripts" / "__pycache__"
            cache.mkdir()
            (cache / "worker.cpython-313.pyc").write_bytes(b"runtime cache")
            after = trusted_host_prepare._candidate_identity(root)["source_sha256"]
            self.assertEqual(after, before)


if __name__ == "__main__":
    unittest.main()
