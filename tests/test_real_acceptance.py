from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
import textwrap
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "teaching"))

import real_acceptance  # noqa: E402


class _ResponsesHandler(BaseHTTPRequestHandler):
    request_count = 0
    authorization_seen = False
    responses_lite_header_seen = False
    input_kind_seen = "unknown"
    body_fields_seen = set()
    response_mode = "success"

    def do_POST(self) -> None:  # noqa: N802
        type(self).request_count += 1
        type(self).authorization_seen = self.headers.get("Authorization") == "Bearer FAKE-API-KEY-SECRET"
        type(self).responses_lite_header_seen = (
            self.headers.get("x-openai-internal-codex-responses-lite") == "true"
        )
        length = int(self.headers.get("Content-Length", "0"))
        request_body = json.loads(self.rfile.read(length))
        type(self).input_kind_seen = "array" if isinstance(request_body.get("input"), list) else "string"
        type(self).body_fields_seen = set(request_body)
        if type(self).response_mode == "auth-error":
            body = json.dumps(
                {
                    "error": {
                        "type": "authentication_error",
                        "code": "invalid_api_key",
                        "message": "FAKE-RESPONSE-SECRET",
                    }
                }
            ).encode("utf-8")
            self.send_response(401)
            self.send_header("Content-Type", "application/json")
            self.send_header("x-request-id", "req_FAKE_REQUEST_ID")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        body = (
            'data: {"type":"response.completed","response":{"usage":'
            '{"input_tokens":3,"output_tokens":1,"total_tokens":4},"output":[]}}\n\n'
        ).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return


class RealAcceptanceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.parent = Path(tempfile.mkdtemp(prefix="ds-lite-real-acceptance-"))
        self.windows = self.parent / "windows"
        self.wsl = self.parent / "wsl"
        self.formal_home = self.parent / "formal-home"
        (self.formal_home / "model-catalogs").mkdir(parents=True)
        (self.formal_home / "model-catalogs" / "catalog.json").write_text(
            '{"models":[{"slug":"gpt-5.6-sol"}]}\n', encoding="utf-8"
        )

    def _write_formal_config(self, base_url: str) -> None:
        (self.formal_home / "config.toml").write_text(
            'model_provider = "custom"\n'
            'model = "gpt-5.6-sol"\n'
            'model_catalog_json = "model-catalogs/catalog.json"\n\n'
            '[model_providers.custom]\n'
            'name = "custom"\n'
            f'base_url = {json.dumps(base_url)}\n'
            'wire_api = "responses"\n'
            'requires_openai_auth = true\n',
            encoding="utf-8",
        )

    def _write_fake_codex(self) -> Path:
        path = self.parent / "codex-0.144.5.py"
        path.write_text(
            textwrap.dedent(
                """
                import json
                import sys

                if "--version" in sys.argv:
                    print("codex-cli 0.144.5")
                elif sys.argv[1:3] == ["features", "list"]:
                    print("hooks stable true")
                    print("multi_agent stable true")
                    print("plugins stable true")
                elif sys.argv[1:3] == ["debug", "models"]:
                    print(json.dumps({"models": [{"slug": "gpt-5.6-sol"}]}))
                else:
                    raise SystemExit(2)
                """
            ).strip()
            + "\n",
            encoding="utf-8",
        )
        return path

    def test_wire_rejection_projection_is_fixed_and_secret_safe(self) -> None:
        cases = (
            ("authentication failed FAKE-SECRET", "auth", "none"),
            ("unknown model requested FAKE-SECRET", "model", "model"),
            ("unknown parameter store FAKE-SECRET", "parameter", "store"),
            ("input must be an array FAKE-SECRET", "input-shape", "input"),
            ("route endpoint was not found FAKE-SECRET", "path", "none"),
            ("malformed json payload FAKE-SECRET", "protocol", "none"),
            ("private vendor rejection FAKE-SECRET", "unknown", "none"),
        )
        for message, expected_class, expected_parameter in cases:
            with self.subTest(message=message):
                projection = real_acceptance.wire_probe._rejection_projection(message)
                self.assertEqual(projection["rejection_class"], expected_class)
                self.assertEqual(projection["parameter"], expected_parameter)
                self.assertNotIn("FAKE-SECRET", str(projection))

    def test_responses_lite_header_variant_is_explicit_and_single_attempt(self) -> None:
        _ResponsesHandler.request_count = 0
        _ResponsesHandler.responses_lite_header_seen = False
        server = ThreadingHTTPServer(("127.0.0.1", 0), _ResponsesHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            self._write_formal_config(f"http://127.0.0.1:{server.server_port}/v1")
            route = real_acceptance.wire_probe.load_provider_route(self.formal_home)
            observed = real_acceptance.wire_probe.probe_responses(
                route,
                api_key="FAKE-API-KEY-SECRET",
                responses_lite_header=True,
            )
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

        self.assertEqual(observed["status"], "passed")
        self.assertTrue(observed["request_shape"]["responses_lite_header_present"])
        self.assertTrue(_ResponsesHandler.responses_lite_header_seen)
        self.assertEqual(_ResponsesHandler.request_count, 1)
        self.assertFalse(observed["automatic_retry_observed"])

    def test_responses_message_array_variant_matches_codex_item_shape(self) -> None:
        _ResponsesHandler.request_count = 0
        _ResponsesHandler.input_kind_seen = "unknown"
        server = ThreadingHTTPServer(("127.0.0.1", 0), _ResponsesHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            self._write_formal_config(f"http://127.0.0.1:{server.server_port}/v1")
            route = real_acceptance.wire_probe.load_provider_route(self.formal_home)
            observed = real_acceptance.wire_probe.probe_responses(
                route,
                api_key="FAKE-API-KEY-SECRET",
                responses_lite_header=True,
                input_kind="message-array",
            )
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

        self.assertEqual(observed["status"], "passed")
        self.assertEqual(observed["request_shape"]["input_kind"], "message-array")
        self.assertEqual(_ResponsesHandler.input_kind_seen, "array")
        self.assertEqual(_ResponsesHandler.request_count, 1)

    def test_codex_lite_minimal_profile_is_explicit_and_redacted(self) -> None:
        _ResponsesHandler.request_count = 0
        _ResponsesHandler.responses_lite_header_seen = False
        _ResponsesHandler.body_fields_seen = set()
        server = ThreadingHTTPServer(("127.0.0.1", 0), _ResponsesHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            self._write_formal_config(f"http://127.0.0.1:{server.server_port}/v1")
            route = real_acceptance.wire_probe.load_provider_route(self.formal_home)
            observed = real_acceptance.wire_probe.probe_responses(
                route,
                api_key="FAKE-API-KEY-SECRET",
                request_profile="codex-lite-minimal",
            )
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

        self.assertEqual(observed["status"], "passed")
        self.assertEqual(observed["request_shape"]["profile"], "codex-lite-minimal")
        self.assertTrue(observed["request_shape"]["responses_lite_header_present"])
        self.assertEqual(observed["request_shape"]["input_kind"], "codex-message-array")
        self.assertTrue(_ResponsesHandler.responses_lite_header_seen)
        self.assertTrue({"model", "input", "tool_choice", "parallel_tool_calls", "reasoning", "store", "stream", "include", "text"}.issubset(_ResponsesHandler.body_fields_seen))
        self.assertEqual(_ResponsesHandler.request_count, 1)
        self.assertNotIn("FAKE-API-KEY-SECRET", str(observed))

    def test_prepare_is_fresh_only_and_uses_fixed_round_schema(self) -> None:
        result = real_acceptance.prepare_roots(
            self.windows,
            self.wsl,
            pilot_id="communication-beta2-20260720-wire-diagnostic-01",
            authorization_ref="user-approved-20260720",
        )
        self.assertEqual(result["schema_version"], "ds-lite.real-acceptance.v1")
        self.assertEqual(result["status"], "prepared")
        self.assertTrue((self.windows / "rounds" / "00-prepare.json").is_file())
        self.assertTrue((self.wsl / "peer-manifest.json").is_file())
        with self.assertRaises(real_acceptance.RealAcceptanceError):
            real_acceptance.prepare_roots(
                self.windows,
                self.parent / "another-wsl",
                pilot_id="communication-beta2-20260720-wire-diagnostic-02",
                authorization_ref="user-approved-20260720",
            )

    def test_prepare_rejects_non_relative_authorization_ref_before_creating_roots(self) -> None:
        invalid_refs = (
            "../authorization.json",
            "/authorization.json",
            r"C:\private\authorization.json",
            "https://approval.example/record",
        )
        for index, authorization_ref in enumerate(invalid_refs):
            windows = self.parent / f"windows-invalid-{index}"
            wsl = self.parent / f"wsl-invalid-{index}"
            with self.subTest(authorization_ref=authorization_ref):
                with self.assertRaisesRegex(real_acceptance.RealAcceptanceError, "authorization"):
                    real_acceptance.prepare_roots(
                        windows,
                        wsl,
                        pilot_id=f"wire-invalid-authorization-{index}",
                        authorization_ref=authorization_ref,
                    )
                self.assertFalse(windows.exists())
                self.assertFalse(wsl.exists())

    def test_preflight_proves_route_fidelity_catalog_cli_and_zero_retries(self) -> None:
        self._write_formal_config("https://provider.example/v1")
        fake_codex = self._write_fake_codex()
        expected_hash = hashlib.sha256(fake_codex.read_bytes()).hexdigest()
        real_acceptance.prepare_roots(
            self.windows,
            self.wsl,
            pilot_id="communication-beta2-20260720-wire-diagnostic-01",
            authorization_ref="user-approved-20260720",
        )

        receipt = real_acceptance.preflight_round(
            self.windows,
            source_codex_home=self.formal_home,
            codex_bin=fake_codex,
            expected_cli_sha256=expected_hash,
            environment={"OPENAI_API_KEY": "FAKE-API-KEY-SECRET"},
        )

        self.assertEqual(receipt["status"], "passed")
        observations = receipt["observations"]
        self.assertTrue(observations["route_fidelity"]["required_fields_match"])
        self.assertTrue(observations["catalog_model_observed"])
        self.assertEqual(observations["authentication_category"], "environment-api-key")
        isolated = (self.windows / "wire-home" / "config.toml").read_text(encoding="utf-8")
        self.assertIn("requires_openai_auth = true", isolated)
        self.assertIn("request_max_retries = 0", isolated)
        self.assertIn("stream_max_retries = 0", isolated)
        serialized = json.dumps(receipt)
        self.assertNotIn("provider.example", serialized)
        self.assertNotIn("FAKE-API-KEY-SECRET", serialized)

    def test_preflight_rejects_a_non_prepared_round_zero(self) -> None:
        self._write_formal_config("https://provider.example/v1")
        fake_codex = self._write_fake_codex()
        real_acceptance.prepare_roots(
            self.windows,
            self.wsl,
            pilot_id="communication-beta2-20260720-wire-diagnostic-01",
            authorization_ref="user-approved-20260720",
        )
        prepare_path = self.windows / "rounds" / "00-prepare.json"
        prepare = json.loads(prepare_path.read_text(encoding="utf-8"))
        prepare["status"] = "blocked"
        prepare_path.write_text(json.dumps(prepare), encoding="utf-8")

        with self.assertRaisesRegex(real_acceptance.RealAcceptanceError, "not prepared"):
            real_acceptance.preflight_round(
                self.windows,
                source_codex_home=self.formal_home,
                codex_bin=fake_codex,
                expected_cli_sha256=hashlib.sha256(fake_codex.read_bytes()).hexdigest(),
                environment={"OPENAI_API_KEY": "FAKE-API-KEY-SECRET"},
            )
        self.assertFalse((self.windows / "wire-home").exists())

    def test_loopback_network_and_responses_are_single_attempt_and_redacted(self) -> None:
        _ResponsesHandler.request_count = 0
        _ResponsesHandler.authorization_seen = False
        server = ThreadingHTTPServer(("127.0.0.1", 0), _ResponsesHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            self._write_formal_config(f"http://127.0.0.1:{server.server_port}/v1")
            fake_codex = self._write_fake_codex()
            real_acceptance.prepare_roots(
                self.windows,
                self.wsl,
                pilot_id="communication-beta2-20260720-wire-diagnostic-01",
                authorization_ref="user-approved-20260720",
            )
            real_acceptance.preflight_round(
                self.windows,
                source_codex_home=self.formal_home,
                codex_bin=fake_codex,
                expected_cli_sha256=hashlib.sha256(fake_codex.read_bytes()).hexdigest(),
                environment={"OPENAI_API_KEY": "FAKE-API-KEY-SECRET"},
            )
            network = real_acceptance.network_round(self.windows, source_codex_home=self.formal_home)
            response = real_acceptance.responses_round(
                self.windows,
                source_codex_home=self.formal_home,
                api_key="FAKE-API-KEY-SECRET",
            )
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

        self.assertEqual(network["status"], "passed")
        self.assertEqual(response["status"], "passed")
        self.assertEqual(response["attempts"]["provider_request_count"], 1)
        self.assertFalse(response["attempts"]["automatic_retry_observed"])
        self.assertEqual(_ResponsesHandler.request_count, 1)
        self.assertTrue(_ResponsesHandler.authorization_seen)
        saved = (self.windows / "rounds" / "03-responses.json").read_text(encoding="utf-8")
        self.assertNotIn("127.0.0.1", saved)
        self.assertNotIn("FAKE-API-KEY-SECRET", saved)
        with self.assertRaises(real_acceptance.RealAcceptanceError):
            real_acceptance.responses_round(
                self.windows,
                source_codex_home=self.formal_home,
                api_key="FAKE-API-KEY-SECRET",
            )

    def test_responses_reduces_status_error_shape_request_id_and_wire_shape(self) -> None:
        _ResponsesHandler.request_count = 0
        _ResponsesHandler.authorization_seen = False
        _ResponsesHandler.response_mode = "auth-error"
        server = ThreadingHTTPServer(("127.0.0.1", 0), _ResponsesHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            self._write_formal_config(f"http://127.0.0.1:{server.server_port}/v1")
            fake_codex = self._write_fake_codex()
            real_acceptance.prepare_roots(
                self.windows,
                self.wsl,
                pilot_id="communication-beta2-20260720-wire-diagnostic-test-error-shape",
                authorization_ref="user-approved-20260720",
            )
            real_acceptance.preflight_round(
                self.windows,
                source_codex_home=self.formal_home,
                codex_bin=fake_codex,
                expected_cli_sha256=hashlib.sha256(fake_codex.read_bytes()).hexdigest(),
                environment={"OPENAI_API_KEY": "FAKE-API-KEY-SECRET"},
            )
            real_acceptance.network_round(self.windows, source_codex_home=self.formal_home)
            receipt = real_acceptance.responses_round(
                self.windows,
                source_codex_home=self.formal_home,
                api_key="FAKE-API-KEY-SECRET",
            )
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
            _ResponsesHandler.response_mode = "success"

        self.assertEqual(receipt["status"], "blocked")
        observations = receipt["observations"]
        self.assertEqual(observations["http_status"], 401)
        self.assertEqual(observations["error_shape"]["error_object_state"], "observed")
        self.assertEqual(observations["error_shape"]["provider_error_type"], "authentication_error")
        self.assertEqual(observations["error_shape"]["provider_error_code"], "invalid_api_key")
        self.assertRegex(observations["request_id_sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(observations["request_shape"]["body_fields"], ["input", "model", "store", "stream"])
        self.assertEqual(observations["codex_wire_comparison"]["status"], "probe-contract-only")
        self.assertEqual(_ResponsesHandler.request_count, 1)
        saved = (self.windows / "rounds" / "03-responses.json").read_text(encoding="utf-8")
        self.assertNotIn("FAKE-RESPONSE-SECRET", saved)
        self.assertNotIn("FAKE_REQUEST_ID", saved)
        self.assertNotIn("127.0.0.1", saved)

    def test_round_validator_rejects_sensitive_and_absolute_values(self) -> None:
        payload = real_acceptance.new_round(
            pilot_id="wire-test",
            round_id="test",
            status="blocked",
            target="test redaction",
            facts=["bounded fact"],
            hypotheses=["bounded hypothesis"],
            authorization_boundary=["no cache changes"],
            commands=["codex --version"],
            observations={"status": "blocked"},
            evidence_refs=["rounds/test.json"],
            failure_layer="transport",
            unverified=["provider"],
            next_action="stop",
        )
        payload["observations"]["token"] = "SECRET"
        with self.assertRaises(real_acceptance.RealAcceptanceError):
            real_acceptance.validate_round(payload)
        payload["observations"] = {"path": r"C:\private\root"}
        with self.assertRaises(real_acceptance.RealAcceptanceError):
            real_acceptance.validate_round(payload)

    def test_cross_platform_entrypoints_and_validator_wiring_exist(self) -> None:
        powershell = REPO_ROOT / "teaching" / "run_real_acceptance.ps1"
        bash = REPO_ROOT / "teaching" / "run_real_acceptance.sh"
        self.assertTrue(powershell.is_file())
        self.assertTrue(bash.is_file())
        self.assertIn("real_acceptance.py", powershell.read_text(encoding="utf-8"))
        self.assertIn("real_acceptance.py", bash.read_text(encoding="utf-8"))
        for action in ("prepare", "preflight", "network", "responses"):
            self.assertIn(action, powershell.read_text(encoding="utf-8"))
            self.assertIn(action, bash.read_text(encoding="utf-8"))
        for validator in (
            REPO_ROOT / "tools" / "validation" / "run_validate.ps1",
            REPO_ROOT / "tools" / "validation" / "run_validate.sh",
        ):
            content = validator.read_text(encoding="utf-8")
            for required in (
                "teaching/wire_probe.py",
                "teaching/real_acceptance.py",
                "teaching/matched_effect.py",
                "teaching/host_acceptance.py",
                "tests/test_real_acceptance.py",
                "tests/test_matched_effect.py",
                "tests/test_host_acceptance.py",
            ):
                self.assertIn(required, content)


if __name__ == "__main__":
    unittest.main()
