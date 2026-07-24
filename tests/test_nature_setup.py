from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "plugins" / "deepscientist-lite" / "scripts"
import sys
sys.path.insert(0, str(SCRIPTS))
import ds_lite_nature_setup  # noqa: E402


class NatureSetupTests(unittest.TestCase):
    def test_capability_matrix_covers_upstream_dependencies_and_fallbacks(self) -> None:
        registry = ds_lite_nature_setup.load_registry(SCRIPTS / "ds_lite_nature_setup.py")
        matrix = ds_lite_nature_setup.capability_matrix(registry)
        self.assertEqual(len(matrix), 17)
        academic = matrix["nature-academic-search"]
        self.assertTrue(academic["route_complete"])
        self.assertTrue(any(path.endswith("requirements.txt") for path in academic["requirements"]))
        self.assertIn("PUBMED_EMAIL", academic["environment_keys"])
        self.assertTrue(academic["local_fallback"])
        patent = matrix["nature-paper-to-patent"]
        self.assertTrue(patent["playwright_optional"])
        self.assertIn("network", patent["external_effects"])

    def test_snapshot_verification_matches_vendor_and_runtime(self) -> None:
        registry = ds_lite_nature_setup.load_registry(SCRIPTS / "ds_lite_nature_setup.py")
        result = ds_lite_nature_setup.verify_snapshot(registry)
        self.assertEqual(result["mismatches"], [], result["mismatches"][:20])
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["skill_count"], 17)
        self.assertFalse(result["shared_layer_discoverable"])

    def test_doctor_redacts_secret_values_and_writes_fresh_guide(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            workspace = Path(raw)
            old = os.environ.get("OPENAI_API_KEY")
            os.environ["OPENAI_API_KEY"] = "SECRET_MARKER"
            try:
                result = ds_lite_nature_setup.run_setup(SimpleNamespace(workspace=str(workspace)), apply_config=False)
            finally:
                if old is None:
                    os.environ.pop("OPENAI_API_KEY", None)
                else:
                    os.environ["OPENAI_API_KEY"] = old
            serialized = json.dumps(result, ensure_ascii=False)
            self.assertNotIn("SECRET_MARKER", serialized)
            runs = list((workspace / ".ds-lite" / "nature" / "runs").iterdir())
            self.assertEqual(len(runs), 1)
            guide = (runs[0] / "README.zh.md").read_text(encoding="utf-8")
            receipt = json.loads((runs[0] / "receipt.json").read_text(encoding="utf-8"))
            self.assertNotIn("SECRET_MARKER", guide)
            self.assertFalse(receipt["secret_values_persisted"])
            self.assertFalse(receipt["observation"]["policy"]["global_config_read"])

    def test_apply_is_local_and_verify_rejects_enabled_without_explicit_configuration(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            workspace = Path(raw)
            ds_lite_nature_setup.run_setup(SimpleNamespace(workspace=str(workspace)), apply_config=True)
            config_path = workspace / ".ds-lite" / "nature" / "integration-config.json"
            self.assertTrue(config_path.is_file())
            config = json.loads(config_path.read_text(encoding="utf-8"))
            self.assertFalse(config["enabled"])
            verified = ds_lite_nature_setup.verify(SimpleNamespace(workspace=str(workspace)))
            self.assertEqual(verified["status"], "passed")
            self.assertEqual(verified["snapshot_status"], "passed")
            with self.assertRaises(ds_lite_nature_setup.SetupError):
                ds_lite_nature_setup.run_setup(SimpleNamespace(workspace=str(workspace)), apply_config=True)


if __name__ == "__main__":
    unittest.main()
