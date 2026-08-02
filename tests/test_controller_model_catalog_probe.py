from __future__ import annotations

import sys
import unittest
import hashlib
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from teaching import controller_model_catalog_probe
from teaching.controller_model_catalog_probe import summarize


class ModelCatalogProbeTests(unittest.TestCase):
    def test_compact_current_schema_pin_matches_generated_manifest(self) -> None:
        schema_root = (
            ROOT / "plugins" / "deepscientist-lite-core" / "schemas" / "codex"
            / "0.146.0-alpha.3.1"
        )
        manifest = json.loads((schema_root / "SCHEMA-MANIFEST.json").read_text(encoding="utf-8"))
        for relative, expected in manifest["files"].items():
            self.assertEqual(
                hashlib.sha256((schema_root / relative).read_bytes()).hexdigest(), expected,
            )

    def test_summary_preserves_selection_metadata_and_is_stable(self) -> None:
        response = {"result": {"data": [{
            "id": "current", "model": "current", "displayName": "Current",
            "hidden": False, "isDefault": True, "upgrade": "next",
        }], "nextCursor": None}}
        first = summarize(response)
        second = summarize(response)
        self.assertEqual(first, second)
        self.assertEqual(first["models"][0]["upgrade"], "next")
        self.assertEqual(len(first["catalog_sha256"]), 64)

    def test_invalid_catalog_fails_closed(self) -> None:
        with self.assertRaises(RuntimeError):
            summarize({"result": {"data": [{"id": "missing-model"}]}})

    def test_proxy_socket_uses_only_the_explicit_proxy_transport(self) -> None:
        commands: list[list[str]] = []

        class FakeProcess:
            def poll(self) -> None:
                return None

            def terminate(self) -> None:
                return None

            def wait(self, timeout: float) -> None:
                return None

        class FakeAdapter:
            def __init__(self, process: object, schema_root: Path, response_timeout: float) -> None:
                self.process = process

            def initialize(self, request_id: str) -> None:
                return None

            def list_models(self, include_hidden: bool, request_id: str) -> SimpleNamespace:
                return SimpleNamespace(response={"result": {"data": [{
                    "id": "gpt-test", "model": "gpt-test", "displayName": "Test",
                    "hidden": False, "isDefault": True, "upgrade": None,
                }]}})

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            args = SimpleNamespace(
                codex_bin=root / "codex.exe",
                codex_version="0.146.0-alpha.3.1",
                schema_root=root / "schema",
                proxy_socket=r"\\.\pipe\codex-ipc",
                home=root / "isolated-home",
                output=root / "catalog.json",
            )
            with patch.object(controller_model_catalog_probe.subprocess, "run",
                              return_value=SimpleNamespace(stdout="codex-cli 0.146.0-alpha.3.1\n")), \
                 patch.object(controller_model_catalog_probe.subprocess, "Popen",
                              side_effect=lambda command, **_: commands.append(command) or FakeProcess()), \
                 patch.object(controller_model_catalog_probe, "AppServerAdapter", FakeAdapter):
                controller_model_catalog_probe.run(args)

        self.assertEqual(
            commands,
            [[str(args.codex_bin.resolve()), "app-server", "proxy", "--sock", r"\\.\pipe\codex-ipc"]],
        )

    def test_transport_failure_is_preserved_as_an_unobserved_receipt(self) -> None:
        class FakeProcess:
            def poll(self) -> None:
                return None

            def terminate(self) -> None:
                return None

            def wait(self, timeout: float) -> None:
                return None

        class FailingAdapter:
            def __init__(self, process: object, schema_root: Path, response_timeout: float) -> None:
                raise RuntimeError("app-server-closed")

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            args = SimpleNamespace(
                codex_bin=root / "codex.exe",
                codex_version="0.146.0-alpha.3.1",
                schema_root=root / "schema",
                proxy_socket=r"\\.\pipe\codex-ipc",
                home=root / "isolated-home",
                output=root / "catalog.json",
            )
            with patch.object(controller_model_catalog_probe.subprocess, "run",
                              return_value=SimpleNamespace(stdout="codex-cli 0.146.0-alpha.3.1\n")), \
                 patch.object(controller_model_catalog_probe.subprocess, "Popen",
                              return_value=FakeProcess()), \
                 patch.object(controller_model_catalog_probe, "AppServerAdapter", FailingAdapter):
                with self.assertRaisesRegex(RuntimeError, "app-server-closed"):
                    controller_model_catalog_probe.run(args)

            receipt = json.loads(args.output.read_text(encoding="utf-8"))
            self.assertEqual(receipt["observation_status"], "unobserved")
            self.assertEqual(receipt["failure_type"], "RuntimeError")
            self.assertFalse(receipt["release_allowed"])

    def test_ambient_home_does_not_copy_or_override_codex_home(self) -> None:
        environments: list[dict[str, str]] = []

        class FakeProcess:
            def poll(self) -> None:
                return None

            def terminate(self) -> None:
                return None

            def wait(self, timeout: float) -> None:
                return None

        class FakeAdapter:
            def __init__(self, process: object, schema_root: Path, response_timeout: float) -> None:
                return None

            def initialize(self, request_id: str) -> None:
                return None

            def list_models(self, include_hidden: bool, request_id: str) -> SimpleNamespace:
                return SimpleNamespace(response={"result": {"data": [{
                    "id": "gpt-test", "model": "gpt-test", "displayName": "Test",
                    "hidden": False, "isDefault": True, "upgrade": None,
                }]}})

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            args = SimpleNamespace(
                codex_bin=root / "codex.exe",
                codex_version="0.146.0-alpha.3.1",
                schema_root=root / "schema",
                proxy_socket=None,
                ambient_home=True,
                home=root / "must-not-be-created",
                output=root / "catalog.json",
            )
            with patch.object(controller_model_catalog_probe.subprocess, "run",
                              return_value=SimpleNamespace(stdout="codex-cli 0.146.0-alpha.3.1\n")), \
                 patch.object(controller_model_catalog_probe.subprocess, "Popen",
                              side_effect=lambda command, **kwargs: environments.append(kwargs["env"]) or FakeProcess()), \
                 patch.object(controller_model_catalog_probe, "AppServerAdapter", FakeAdapter):
                receipt = controller_model_catalog_probe.run(args)

            self.assertFalse(args.home.exists())
            self.assertNotIn("CODEX_HOME", environments[0])
            self.assertEqual(receipt["home_mode"], "ambient")
            self.assertFalse(receipt["release_allowed"])


if __name__ == "__main__":
    unittest.main()
