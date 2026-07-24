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
            parsed = json.loads((root / "pilot" / "preparation.json").read_text(encoding="utf-8"))
            self.assertEqual(parsed["retries"]["request_max_retries"], 0)
            self.assertNotIn("https://", json.dumps(parsed))

    def test_existing_root_is_not_overwritten(self):
        with tempfile.TemporaryDirectory(dir=os.environ.get("TEMP")) as directory:
            root = Path(directory)
            binary = root / "codex.exe"; binary.write_bytes(b"pinned")
            source = self._source(root); pilot = root / "pilot"; pilot.mkdir(); marker = pilot / "marker"; marker.write_text("keep")
            with patch.object(trusted_host_prepare, "_sha256", return_value=trusted_host_prepare.EXPECTED_SHA256):
                with self.assertRaises(trusted_host_prepare.PreparationError):
                    trusted_host_prepare.prepare(codex_bin=binary, source_home=source, repo_root=root, pilot_root=pilot, install=False)
            self.assertEqual(marker.read_text(), "keep")

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


if __name__ == "__main__":
    unittest.main()
