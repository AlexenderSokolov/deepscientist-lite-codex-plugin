from __future__ import annotations

import json
import io
import subprocess
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "plugins" / "deepscientist-lite-web" / "scripts" / "ds_lite_extensions.py"
KNOWLEDGE_SCRIPT = ROOT / "plugins" / "deepscientist-lite-knowledge" / "scripts" / "ds_lite_knowledge.py"
SCRIPT_DIR = SCRIPT.parent
KNOWLEDGE_SCRIPT_DIR = KNOWLEDGE_SCRIPT.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
if str(KNOWLEDGE_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(KNOWLEDGE_SCRIPT_DIR))

try:
    import ds_lite_extensions
    import ds_lite_knowledge
except ModuleNotFoundError:
    ds_lite_extensions = None
    ds_lite_knowledge = None


class ExtensionProtocolTests(unittest.TestCase):
    def test_cli_emission_is_ascii_safe_for_legacy_windows_consoles(self) -> None:
        self.assertIsNotNone(ds_lite_extensions)
        stream = io.StringIO()
        with mock.patch.object(sys, "stdout", stream):
            ds_lite_extensions._emit_json({"message": "中文 source record"})
        self.assertEqual(
            stream.getvalue(),
            '{"message": "\\u4e2d\\u6587 source record"}\n',
        )

    def capability(self) -> dict:
        return {
            "schema_version": "ds-lite.capability.v1",
            "backend_id": "playwright-cli",
            "backend_version": "not-observed",
            "capabilities": ["fetch", "render", "interact"],
            "authentication": "none",
            "storage_boundary": "project",
            "availability": "not-observed",
            "observed_at": "2026-07-24T00:00:00Z",
            "extensions": {},
        }

    def source_record(self) -> dict:
        return {
            "schema_version": "ds-lite.source-record.v1",
            "source_id": "source-example",
            "source_uri": "https://example.com/article",
            "retrieved_at": "2026-07-24T00:00:00Z",
            "content_sha256": "a" * 64,
            "media_type": "text/html",
            "backend_id": "stdlib-http",
            "transformations": ["capture", "normalize"],
            "artifact_refs": ["research/sources/source-example/content.html"],
            "status": "captured",
            "failure_layer": "none",
            "unverified_items": [],
            "policy": {
                "public_only": True,
                "authenticated": False,
                "submitted_forms": False,
                "cookies_persisted": False,
            },
            "extensions": {},
        }

    def source_record_v2(self, status: str = "captured") -> dict:
        payload = {
            "schema_version": "ds-lite.source-record.v2",
            "source_id": "source-v2",
            "source_uri": "https://example.com/article",
            "retrieved_at": "2026-07-24T00:00:00Z",
            "content_sha256": "b" * 64,
            "media_type": "text/html",
            "backend_id": "stdlib-http",
            "transformations": ["http-get"],
            "artifact_refs": ["research/sources/source-v2/content.html"],
            "status": status,
            "failure_layer": "none",
            "unverified_items": [],
            "policy": {"public_only": True, "authenticated": False, "submitted_forms": False, "cookies_persisted": False},
            "failure_reason": "",
            "budget": {"pages": 1, "bytes": 12, "seconds": 1},
            "extensions": {},
        }
        if status in {"failed", "not-observed"}:
            payload.update({"content_sha256": "", "media_type": "", "artifact_refs": [], "failure_layer": "network", "failure_reason": "timeout"})
        return payload

    def proposal(self) -> dict:
        return {
            "schema_version": "ds-lite.knowledge-proposal.v1",
            "proposal_id": "proposal-example",
            "target": "researchkb",
            "source_refs": ["research/sources/source-example/source-record.json"],
            "summary": "A reviewable candidate summary.",
            "claims": [
                {
                    "text": "The source documents a bounded example.",
                    "source_refs": ["research/sources/source-example/source-record.json"],
                    "uncertainty": "The source has not been independently corroborated.",
                }
            ],
            "review_status": "pending",
            "review_ref": "",
            "created_at": "2026-07-24T00:00:00Z",
            "extensions": {},
        }

    def test_valid_protocols_are_accepted(self) -> None:
        self.assertIsNotNone(ds_lite_extensions)
        self.assertIsNotNone(ds_lite_knowledge)
        self.assertEqual(ds_lite_extensions.validate_capability(self.capability()), self.capability())
        self.assertEqual(ds_lite_extensions.validate_source_record(self.source_record()), self.source_record())
        self.assertEqual(ds_lite_knowledge.validate_proposal(self.proposal()), self.proposal())

    def test_source_record_is_public_only_and_secret_safe(self) -> None:
        payload = self.source_record()
        payload["policy"]["authenticated"] = True
        with self.assertRaisesRegex(ds_lite_extensions.ExtensionProtocolError, "public-only"):
            ds_lite_extensions.validate_source_record(payload)

        payload = self.source_record()
        payload["extensions"] = {"cookie": "secret"}
        with self.assertRaisesRegex(ds_lite_extensions.ExtensionProtocolError, "sensitive"):
            ds_lite_extensions.validate_source_record(payload)

    def test_source_record_rejects_non_http_and_path_escape(self) -> None:
        payload = self.source_record()
        payload["source_uri"] = "file:///private/data.txt"
        with self.assertRaisesRegex(ds_lite_extensions.ExtensionProtocolError, "http"):
            ds_lite_extensions.validate_source_record(payload)

        payload = self.source_record()
        payload["artifact_refs"] = ["../private/content.html"]
        with self.assertRaisesRegex(ds_lite_extensions.ExtensionProtocolError, "artifact_refs"):
            ds_lite_extensions.validate_source_record(payload)

    def test_v2_source_records_require_content_for_success_and_failure_layer_for_failure(self) -> None:
        self.assertEqual(
            ds_lite_extensions.validate_source_record_v2(self.source_record_v2())["schema_version"],
            "ds-lite.source-record.v2",
        )
        failed = self.source_record_v2("failed")
        self.assertEqual(ds_lite_extensions.validate_source_record_v2(failed)["status"], "failed")
        failed["failure_layer"] = "none"
        with self.assertRaisesRegex(ds_lite_extensions.ExtensionProtocolError, "failure layer"):
            ds_lite_extensions.validate_source_record_v2(failed)

    def test_knowledge_adapter_rejects_suffixed_sensitive_keys(self) -> None:
        payload = self.proposal()
        payload["extensions"] = {"provider_api_key": "do-not-store"}
        with self.assertRaisesRegex(ds_lite_knowledge.KnowledgeError, "sensitive"):
            ds_lite_knowledge.validate_proposal(payload)

    def test_proposal_cannot_publish_without_review(self) -> None:
        payload = self.proposal()
        payload["review_status"] = "accepted"
        with self.assertRaisesRegex(ds_lite_knowledge.KnowledgeError, "review_ref"):
            ds_lite_knowledge.validate_proposal(payload)

        payload["review_ref"] = "research/reviews/proposal-example.md"
        self.assertEqual(ds_lite_knowledge.validate_proposal(payload), payload)

    def test_cli_validates_all_three_protocols(self) -> None:
        root = Path(tempfile.mkdtemp(prefix="ds-lite-extension-protocol-"))
        for command, payload in (
            ("validate-capability", self.capability()),
            ("validate-source-record", self.source_record()),
        ):
            with self.subTest(command=command):
                path = root / f"{command}.json"
                path.write_text(json.dumps(payload), encoding="utf-8")
                completed = subprocess.run(
                    [sys.executable, str(SCRIPT), command, "--path", str(path)],
                    text=True,
                    encoding="utf-8",
                    capture_output=True,
                )
                self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
                self.assertTrue(json.loads(completed.stdout)["ok"])
        proposal_path = root / "validate-knowledge-proposal.json"
        proposal_path.write_text(json.dumps(self.proposal()), encoding="utf-8")
        completed = subprocess.run(
            [sys.executable, str(KNOWLEDGE_SCRIPT), "validate", "--path", str(proposal_path)],
            text=True,
            encoding="utf-8",
            capture_output=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertEqual(json.loads(completed.stdout)["status"], "passed")

    def test_pack_doctor_fails_closed_without_matching_core(self) -> None:
        missing = subprocess.run(
            [sys.executable, str(SCRIPT), "doctor"],
            text=True,
            encoding="utf-8",
            capture_output=True,
        )
        self.assertEqual(missing.returncode, 2)
        self.assertEqual(json.loads(missing.stdout)["status"], "blocked")

        passed = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "doctor",
                "--core-root",
                str(ROOT / "plugins" / "deepscientist-lite-core"),
            ],
            text=True,
            encoding="utf-8",
            capture_output=True,
        )
        self.assertEqual(passed.returncode, 0, passed.stdout + passed.stderr)
        self.assertEqual(json.loads(passed.stdout)["status"], "passed")

    def test_doctor_discovers_explicit_isolated_playwright_runtime(self) -> None:
        runtime = Path(tempfile.mkdtemp(prefix="ds-lite-playwright-runtime-"))
        result = ds_lite_extensions.backend_doctor(str(runtime))
        playwright = next(item for item in result["backends"] if item["backend_id"] == "playwright-cli")
        self.assertTrue(playwright["available"])
        self.assertTrue(playwright["isolated_runtime"])

    def test_web_search_and_render_require_explicit_external_authorization(self) -> None:
        search = subprocess.run(
            [sys.executable, str(SCRIPT), "search", "--query", "test", "--project-root", str(ROOT), "--output", "research/search.json"],
            text=True, encoding="utf-8", capture_output=True,
        )
        self.assertEqual(search.returncode, 2)
        self.assertEqual(json.loads(search.stdout)["failure_layer"], "authorization")
        render = subprocess.run(
            [sys.executable, str(SCRIPT), "render", "--url", "https://example.com", "--project-root", str(ROOT), "--output", "research/page.md", "--record-output", "research/page.json", "--source-id", "page"],
            text=True, encoding="utf-8", capture_output=True,
        )
        self.assertEqual(render.returncode, 2)
        self.assertEqual(json.loads(render.stdout)["failure_layer"], "authorization")

    def test_web_scope_is_fail_closed_before_fetch(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "fetch",
                "--url",
                "https://example.com/article",
                "--project-root",
                str(ROOT),
                "--output",
                "research/should-not-be-created.html",
                "--record-output",
                "research/should-not-be-created.json",
                "--source-id",
                "scope-test",
            ],
            text=True,
            encoding="utf-8",
            capture_output=True,
        )
        self.assertEqual(completed.returncode, 2)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["failure_layer"], "policy")
        self.assertIn("allowed domain", payload["reason"])

    def test_opencli_rejects_non_public_adapter_before_process_start(self) -> None:
        args = SimpleNamespace(
            project_root=str(ROOT), output="research/opencli.json", record_output="research/opencli-record.json",
            source_id="opencli-test", url="https://example.com", allowed_domains=["example.com"],
            site="fake", opencli_command="login", opencli_arg=[], opencli_version="1.8.6",
            timeout=1.0, max_bytes=1000,
        )
        with mock.patch.object(ds_lite_extensions, "_opencli_manifest_path", return_value=Path(tempfile.mkdtemp()) / "manifest.json"), \
             mock.patch.object(ds_lite_extensions.shutil, "which", return_value="opencli"), \
             mock.patch.object(ds_lite_extensions.subprocess, "run") as run:
            manifest = Path(ds_lite_extensions._opencli_manifest_path())
            manifest.write_text(json.dumps([{"site": "fake", "name": "login", "access": "write", "strategy": "COOKIE", "browser": True}]), encoding="utf-8")
            result, code = ds_lite_extensions._opencli(args)
        self.assertEqual(code, 2)
        self.assertEqual(result["failure_layer"], "policy")
        run.assert_not_called()

    def test_opencli_public_adapter_writes_source_record_v2(self) -> None:
        root = Path(tempfile.mkdtemp(prefix="ds-lite-opencli-"))
        manifest = root / "manifest.json"
        manifest.write_text(json.dumps([{"site": "arxiv", "name": "search", "access": "read", "strategy": "PUBLIC", "browser": False, "domain": "export.arxiv.org"}]), encoding="utf-8")
        args = SimpleNamespace(
            project_root=str(root), output="research/opencli.json", record_output="research/opencli-record.json",
            source_id="opencli-test", url="https://export.arxiv.org", allowed_domains=["export.arxiv.org"],
            site="arxiv", opencli_command="search", opencli_arg=["attention"], opencli_version="1.8.6",
            timeout=1.0, max_bytes=1000,
        )
        completed = subprocess.CompletedProcess(["opencli"], 0, stdout='[{"id":"arxiv:1"}]', stderr="")
        with mock.patch.object(ds_lite_extensions, "_opencli_manifest_path", return_value=manifest), \
             mock.patch.object(ds_lite_extensions.shutil, "which", return_value="opencli"), \
             mock.patch.object(ds_lite_extensions.subprocess, "run", return_value=completed):
            result, code = ds_lite_extensions._opencli(args)
        self.assertEqual(code, 0, result)
        self.assertEqual(result["source_record"]["schema_version"], "ds-lite.source-record.v2")
        self.assertTrue((root / "research" / "opencli-record.json").is_file())

    def test_playwright_render_failure_writes_failed_source_record(self) -> None:
        root = Path(tempfile.mkdtemp(prefix="ds-lite-playwright-render-"))
        args = SimpleNamespace(
            project_root=str(root), url="https://example.com", output="research/page.txt",
            record_output="research/page.json", source_id="playwright-timeout", timeout=1.0,
            max_bytes=1000, allowed_domains=["example.com"], node_bin="node", playwright_module="playwright",
        )
        with mock.patch.object(ds_lite_extensions.subprocess, "run", side_effect=subprocess.TimeoutExpired(["node"], 1)):
            result, code = ds_lite_extensions.render_playwright(args)
        self.assertEqual(code, 2)
        self.assertEqual(result["failure_layer"], "render")
        record = json.loads((root / "research" / "page.json").read_text(encoding="utf-8"))
        self.assertEqual(record["status"], "failed")
        self.assertEqual(record["backend_id"], "playwright-cli")
        self.assertEqual(record["artifact_refs"], [])

    def test_playwright_render_classifies_sanitized_child_failure(self) -> None:
        root = Path(tempfile.mkdtemp(prefix="ds-lite-playwright-child-"))
        args = SimpleNamespace(
            project_root=str(root), url="https://example.com", output="research/page.txt",
            record_output="research/page.json", source_id="playwright-network", timeout=1.0,
            max_bytes=1000, allowed_domains=["example.com"], node_bin="node", playwright_module="playwright",
        )
        completed = subprocess.CompletedProcess(["node"], 1, stdout='{"error_category":"network"}', stderr="")
        with mock.patch.object(ds_lite_extensions.subprocess, "run", return_value=completed):
            result, code = ds_lite_extensions.render_playwright(args)
        self.assertEqual(code, 2)
        self.assertIn("network", result["reason"])
        record = json.loads((root / "research" / "page.json").read_text(encoding="utf-8"))
        self.assertIn("network", record["failure_reason"])

    def test_firecrawl_search_rejects_out_of_scope_result(self) -> None:
        self.assertIsNotNone(ds_lite_extensions)
        args = SimpleNamespace(
            project_root=str(ROOT),
            query="public research",
            max_results=5,
            timeout=3.0,
            max_bytes=10000,
            authorized_external_provider=True,
            allowed_domains=["allowed.example"],
            output="research/search-scope-test.json",
        )
        response = {"success": True, "data": [{"url": "https://outside.example/article", "title": "out"}]}
        with mock.patch.object(ds_lite_extensions, "_firecrawl_request", return_value=response):
            payload, code = ds_lite_extensions._firecrawl_search(args)
        self.assertEqual(code, 2)
        self.assertEqual(payload["failure_layer"], "policy")
        self.assertIn("allowed domain", payload["reason"])

    def test_firecrawl_provider_failures_are_classified_without_leaking_credentials(self) -> None:
        self.assertIsNotNone(ds_lite_extensions)

        class Response:
            status = 200

            def __init__(self, raw: bytes):
                self.raw = raw

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self, _limit: int) -> bytes:
                return self.raw

        cases = [
            (urllib.error.HTTPError("https://api.firecrawl.dev/v1/search", 429, "rate", {}, None), "HTTP 429"),
            (urllib.error.URLError("timed out"), "network failure"),
            (Response(b"not-json"), "invalid JSON"),
        ]
        with mock.patch.dict("os.environ", {"FIRECRAWL_API_KEY": "secret-for-test"}, clear=False):
            for response, expected in cases:
                with self.subTest(expected=expected):
                    patch_kwargs = {"return_value": response} if isinstance(response, Response) else {"side_effect": response}
                    with mock.patch("urllib.request.urlopen", **patch_kwargs):
                        with self.assertRaises(ds_lite_extensions.ExtensionProtocolError) as raised:
                            ds_lite_extensions._firecrawl_request("search", {"query": "x"}, timeout=1, max_bytes=1000)
                    self.assertIn(expected, str(raised.exception))
                    self.assertNotIn("secret-for-test", str(raised.exception))

    def test_firecrawl_render_writes_v2_record_after_scope_check(self) -> None:
        self.assertIsNotNone(ds_lite_extensions)
        root = Path(tempfile.mkdtemp(prefix="ds-lite-firecrawl-render-"))
        args = SimpleNamespace(
            project_root=str(root),
            url="https://allowed.example/article",
            output=str(root / "research" / "article.md"),
            record_output=str(root / "research" / "article.json"),
            source_id="article",
            timeout=3.0,
            max_bytes=10000,
            authorized_external_provider=True,
            allowed_domains=["allowed.example"],
        )
        response = {"success": True, "data": {"markdown": "# Captured\n\nPublic text."}}
        with mock.patch.object(ds_lite_extensions, "_firecrawl_request", return_value=response):
            payload, code = ds_lite_extensions._firecrawl_render(args)
        self.assertEqual(code, 0)
        self.assertEqual(payload["source_record"]["schema_version"], "ds-lite.source-record.v2")
        self.assertEqual(payload["source_record"]["artifact_refs"], ["research/article.md"])

    def test_record_source_hashes_project_artifact_and_keeps_public_policy(self) -> None:
        root = Path(tempfile.mkdtemp(prefix="ds-lite-web-record-"))
        artifact = root / "research" / "sources" / "example.html"
        artifact.parent.mkdir(parents=True)
        artifact.write_text("<html>public</html>", encoding="utf-8")
        output = artifact.parent / "source-record.json"
        completed = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "record-source",
                "--project-root",
                str(root),
                "--artifact",
                str(artifact),
                "--output",
                str(output),
                "--source-id",
                "example",
                "--source-uri",
                "https://example.com/article",
                "--backend-id",
                "playwright-cli",
                "--media-type",
                "text/html",
            ],
            text=True,
            encoding="utf-8",
            capture_output=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        record = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(record["artifact_refs"], ["research/sources/example.html"])
        self.assertEqual(
            record["policy"],
            {
                "public_only": True,
                "authenticated": False,
                "submitted_forms": False,
                "cookies_persisted": False,
            },
        )

    def test_tapestry_and_scholaraio_adapters_only_emit_pending_proposals(self) -> None:
        for adapter, item_key in (("tapestry", "items"), ("scholaraio", "papers")):
            with self.subTest(adapter=adapter):
                root = Path(tempfile.mkdtemp(prefix=f"ds-lite-{adapter}-"))
                source_ref = "research/sources/example/source-record.json"
                handoff = {
                    "schema_version": f"ds-lite.{adapter}-handoff.v1",
                    item_key: [
                        {
                            "id": "example",
                            "title": "Example",
                            "summary": "Review this candidate.",
                            "source_refs": [source_ref],
                            "claims": [
                                {
                                    "text": "A bounded claim.",
                                    "source_refs": [source_ref],
                                    "uncertainty": "Not independently corroborated.",
                                }
                            ],
                        }
                    ],
                }
                input_path = root / "handoff.json"
                output_path = root / "review-queue" / "proposals.json"
                input_path.write_text(json.dumps(handoff), encoding="utf-8")
                completed = subprocess.run(
                    [
                        sys.executable,
                        str(KNOWLEDGE_SCRIPT),
                        f"adapt-{adapter}",
                        "--input",
                        str(input_path),
                        "--target",
                        "researchkb",
                        "--output",
                        str(output_path),
                    ],
                    text=True,
                    encoding="utf-8",
                    capture_output=True,
                )
                self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
                envelope = json.loads(output_path.read_text(encoding="utf-8"))
                self.assertEqual(envelope["review_status"], "pending")
                self.assertEqual(envelope["proposals"][0]["review_status"], "pending")
                self.assertEqual(envelope["proposals"][0]["review_ref"], "")


if __name__ == "__main__":
    unittest.main()
