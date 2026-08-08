from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from teaching.fresh_runtime_candidate_acceptance import (
    AppServerClosed,
    FreshRuntimeCandidateError,
    app_server_command,
    candidate_core_root,
    client_notification_methods,
    failure_layer,
    formal_binding,
    schema_binding,
    validate_provider_session,
)


DIGEST = "a" * 64
PACKAGE_DIGEST = "b" * 64


def formal_receipt() -> dict:
    return {
        "schema_version": "ds-lite.formal-cache-acceptance.v1",
        "status": "passed",
        "candidate_digest": DIGEST,
        "package_digest": PACKAGE_DIGEST,
        "model_request_made": False,
        "marketplace_source": "explicit-candidate-projection",
        "cli_identity": {"expected_version": "0.146.0", "observed_version": "0.146.0", "sha256": "c" * 64},
        "schema_identity": {"manifest_sha256": "d" * 64, "bundle_sha256": "e" * 64},
        "expected_packages": {"deepscientist-lite": "0.10.0-beta.3"},
        "observed_packages": {"deepscientist-lite": "0.10.0-beta.3"},
        "expected_skill_inventory": {"deepscientist-lite": ["ds-lite"]},
        "observed_skill_inventory": {"deepscientist-lite": ["ds-lite"]},
    }


class FreshRuntimeCandidateTests(unittest.TestCase):
    def test_provider_session_requires_explicit_redacted_read_contract(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "provider-session.json"
            path.write_text(json.dumps({
                "schema_version": "ds-lite.provider-session.v1",
                "destination": "codex-app-server", "authorized": True,
                "provider_ref": "ambient-approved", "model_ref": "declared-default",
                "workspace_ref": ".", "fresh_thread": True,
                "allowed_effects": ["read"], "prompt": "Return OK without tools.",
            }), encoding="utf-8")
            session = validate_provider_session(path, Path(directory))
            self.assertEqual(session["allowed_effects"], ["read"])
            self.assertEqual(len(session["prompt_sha256"]), 64)
            path.write_text(json.dumps({**json.loads(path.read_text(encoding="utf-8")), "api_key": "redacted"}), encoding="utf-8")
            with self.assertRaisesRegex(FreshRuntimeCandidateError, "redacted"):
                validate_provider_session(path, Path(directory))
    def test_app_server_uses_the_verified_direct_cli_command(self) -> None:
        self.assertEqual(app_server_command(Path("codex.cmd")), ["codex.cmd", "app-server"])

    def test_host_errors_are_not_persisted_as_raw_failure_text(self) -> None:
        self.assertEqual(failure_layer(FileNotFoundError(2, "private host path")), "host-filesystem-or-process")
        self.assertEqual(failure_layer(AppServerClosed("internal detail")), "app-server-closed")

    def test_candidate_core_root_must_resolve_inside_the_cache(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            core = home / "plugins" / "cache" / "deepscientist-lite" / "deepscientist-lite" / "0.10.0-beta.3"
            (core / "scripts").mkdir(parents=True)
            (core / "scripts" / "ds_lite_autonomy.py").write_text("# fixture\n", encoding="utf-8")
            self.assertEqual(candidate_core_root(home, {"deepscientist-lite": "0.10.0-beta.3"}), core)
            with self.assertRaisesRegex(FreshRuntimeCandidateError, "identity"):
                candidate_core_root(home, {})

    def test_aggregated_candidate_schema_exposes_initialized(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "codex_app_server_protocol.v2.schemas.json").write_text('{"title":"InitializeRequest","method":"initialize"}\n', encoding="utf-8")
            self.assertEqual(client_notification_methods(root), ({"initialized"}, "candidate-aggregate-initialize-default"))

    def test_formal_binding_requires_explicit_candidate_and_matching_digests(self) -> None:
        binding = formal_binding(formal_receipt(), DIGEST, PACKAGE_DIGEST)
        self.assertTrue(all(binding["checks"].values()))
        with self.assertRaisesRegex(FreshRuntimeCandidateError, "binding"):
            formal_binding({**formal_receipt(), "marketplace_source": "repository-projection"}, DIGEST, PACKAGE_DIGEST)
        with self.assertRaisesRegex(FreshRuntimeCandidateError, "binding"):
            formal_binding({**formal_receipt(), "candidate_digest": "f" * 64}, DIGEST, PACKAGE_DIGEST)

    def test_schema_binding_rejects_digest_drift(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payload = root / "v2" / "ThreadStartParams.json"
            payload.parent.mkdir()
            payload.write_text("{}\n", encoding="utf-8")
            file_digest = hashlib.sha256(payload.read_bytes()).hexdigest()
            manifest = {"schema_version": "ds-lite.codex-schema-pin.v1", "codex_version": "0.146.0", "files": {"v2/ThreadStartParams.json": file_digest}}
            manifest_path = root / "SCHEMA-MANIFEST.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            identity = {
                "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
                "bundle_sha256": hashlib.sha256(json.dumps({"v2/ThreadStartParams.json": file_digest}, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest(),
            }
            self.assertTrue(all(schema_binding(root, "0.146.0", identity).values()))
            payload.write_text('{"drift": true}\n', encoding="utf-8")
            with self.assertRaisesRegex(FreshRuntimeCandidateError, "drifted"):
                schema_binding(root, "0.146.0", identity)

    def test_standalone_entry_bootstraps_the_repository_import_path(self) -> None:
        script = (Path(__file__).resolve().parents[1] / "teaching" / "fresh_runtime_candidate_acceptance.py").read_text(encoding="utf-8")
        self.assertIn('if __package__ in {None, ""}:', script)
        self.assertIn("sys.path.insert(0, str(repo_root))", script)

    def test_candidate_runtime_wrappers_require_an_explicit_provider_session(self) -> None:
        root = Path(__file__).resolve().parents[1]
        runners = root / "tools" / "validation" / "runners"
        powershell = (runners / "run_accept_fresh_runtime_candidate.ps1").read_text(encoding="utf-8")
        bash = (runners / "run_accept_fresh_runtime_candidate.sh").read_text(encoding="utf-8")
        for required in ("$ProviderSession", "--provider-session", "fresh_runtime_candidate_acceptance.py"):
            self.assertIn(required, powershell)
        self.assertIn("set -euo pipefail", bash)
        self.assertIn("fresh_runtime_candidate_acceptance.py", bash)


if __name__ == "__main__":
    unittest.main()
