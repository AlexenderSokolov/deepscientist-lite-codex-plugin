from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from teaching import matched_blind_reviewer as reviewer


class BlindReviewerTests(unittest.TestCase):
    def test_output_schema_locks_aliases_and_score_bounds(self) -> None:
        aliases = [f"item-{index:02d}" for index in range(12)]
        schema = reviewer.output_schema(aliases)
        items = schema["properties"]["scores"]["items"]
        self.assertEqual(items["properties"]["alias"]["enum"], aliases)
        self.assertEqual(schema["properties"]["scores"]["minItems"], 12)
        self.assertFalse(items["additionalProperties"])

    def test_reduce_events_requires_one_terminal_thread_and_valid_scores(self) -> None:
        scores = []
        for index in range(12):
            row = {"alias": f"item-{index:02d}", "unsupported_completion_count": 0}
            row.update({metric: 3 for metric in reviewer.matched_effect.EXPRESSION_METRICS})
            scores.append(row)
        payload = {"schema_version": "ds-lite.blind-expression-score.v1", "scores": scores}
        lines = [
            json.dumps({"type": "thread.started", "thread_id": "thread-1"}),
            json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": json.dumps(payload)}}),
            json.dumps({"type": "turn.completed", "usage": {"input_tokens": 10, "output_tokens": 5}}),
        ]
        reduced = reviewer.reduce_events(lines)
        self.assertEqual(reduced["usage_total_tokens"], 15)
        self.assertEqual(len(reduced["scores"]["scores"]), 12)
        with self.assertRaises(reviewer.BlindReviewError):
            reviewer.reduce_events(lines + [json.dumps({"type": "thread.started", "thread_id": "thread-2"})])

    def test_failed_review_is_reduced_without_raw_provider_or_model_text(self) -> None:
        marker = "FAKE-SECRET-REVIEW-OUTPUT"
        receipt = reviewer.redact_failure(
            stdout_lines=[
                json.dumps({"type": "thread.started", "thread_id": "thread-private"}),
                json.dumps({"type": "turn.failed", "error": {"type": "server_error", "message": marker}}),
            ],
            stderr=f"HTTP 503 service unavailable {marker}\n",
            returncode=1,
            reason="process-failed",
        )
        self.assertEqual(receipt["status"], "blocked")
        self.assertEqual(receipt["failure_class"], "protocol")
        self.assertEqual(receipt["http_status_category"], "5xx")
        self.assertEqual(receipt["thread_count"], 1)
        self.assertNotIn(marker, json.dumps(receipt))

    def test_prepare_reviewer_home_copies_only_nonsecret_provider_route(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            source = root / "source"
            source.mkdir()
            (source / "model-catalogs").mkdir()
            (source / "model-catalogs" / "catalog.json").write_text("{}\n", encoding="utf-8")
            (source / "config.toml").write_text(
                '\n'.join(
                    [
                        'model_provider = "custom"',
                        'model_catalog_json = "model-catalogs/catalog.json"',
                        '',
                        '[model_providers.custom]',
                        'name = "test-provider"',
                        'base_url = "https://example.invalid/v1"',
                        'wire_api = "responses"',
                        'requires_openai_auth = true',
                        'api_key = "must-not-copy"',
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            target = root / "reviewer"
            receipt = reviewer.prepare_reviewer_home(source_home=source, target_home=target)
            config = (target / "config.toml").read_text(encoding="utf-8")
            self.assertEqual(receipt["status"], "passed")
            self.assertFalse(receipt["credential_files_copied"])
            self.assertIn('model_provider = "custom"', config)
            self.assertNotIn("must-not-copy", config)
            self.assertTrue((target / "reviewer-home-preparation.json").is_file())

    def test_prepare_reviewer_home_fails_closed_without_provider_route(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            source = root / "source"
            source.mkdir()
            with self.assertRaises(reviewer.BlindReviewError):
                reviewer.prepare_reviewer_home(source_home=source, target_home=root / "reviewer")
            receipt = json.loads(
                (root / "reviewer" / "reviewer-home-preparation.json").read_text(encoding="utf-8")
            )
            self.assertEqual(receipt["status"], "blocked")

    def test_ambient_home_environment_does_not_override_codex_home(self) -> None:
        with mock.patch.dict("os.environ", {"CODEX_HOME": "ambient-marker"}, clear=False):
            environment = reviewer.codex_environment(Path("unused"), ambient_home=True)
        self.assertNotIn("CODEX_HOME", environment)

    def test_isolated_home_environment_uses_exact_home(self) -> None:
        home = Path("isolated-reviewer-home").resolve()
        environment = reviewer.codex_environment(home, ambient_home=False)
        self.assertEqual(environment["CODEX_HOME"], str(home))

    def test_parse_codex_version_accepts_only_registered_phase5_reviewers(self) -> None:
        self.assertEqual(
            reviewer.parse_codex_version("codex-cli 0.146.0-alpha.9.2\n"),
            "0.146.0-alpha.9.2",
        )
        with self.assertRaises(reviewer.BlindReviewError):
            reviewer.parse_codex_version("codex-cli 9.9.9\n")

    def test_import_desktop_review_validates_aliases_and_hashes_identity(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            blind = root / "blind-review"
            blind.mkdir()
            aliases = [f"item-{index:02d}" for index in range(12)]
            (blind / "blind-items.json").write_text(
                json.dumps({"items": [{"alias": alias} for alias in aliases]}),
                encoding="utf-8",
            )
            rows = []
            for alias in aliases:
                row = {"alias": alias, "unsupported_completion_count": 0}
                row.update({metric: 3 for metric in reviewer.matched_effect.EXPRESSION_METRICS})
                rows.append(row)
            source = root / "desktop-scores.json"
            source.write_text(
                json.dumps({"schema_version": "ds-lite.blind-expression-score.v1", "scores": rows}),
                encoding="utf-8",
            )
            result = reviewer.import_desktop_review(
                pilot_root=root,
                scores_path=source,
                output_root=root / "blind-review-result",
                thread_id="desktop-thread",
                turn_id="desktop-turn",
            )
            execution = json.loads(
                (root / "blind-review-result" / "blind-review-execution.json").read_text(encoding="utf-8")
            )
            self.assertEqual(result["status"], "passed")
            self.assertEqual(result["host_class"], "desktop-app-projectless")
            self.assertNotIn("desktop-thread", json.dumps(result))
            self.assertIsNone(execution["usage"]["total_tokens"])
            self.assertFalse(execution["mapping_available_to_reviewer"])


if __name__ == "__main__":
    unittest.main()
