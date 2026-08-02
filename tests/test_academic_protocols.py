from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
ACADEMIC = ROOT / "plugins" / "deepscientist-lite-academic"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


citation = load_module(
    "ds_lite_citation_check",
    ACADEMIC / "scripts" / "ds_lite_citation_check.py",
)
revision = load_module(
    "ds_lite_revision_guard",
    ACADEMIC / "scripts" / "ds_lite_revision_guard.py",
)
live_acceptance = load_module(
    "academic_live_provider_acceptance",
    ROOT / "tools" / "validation" / "academic_live_provider_acceptance.py",
)


class CitationProtocolTests(unittest.TestCase):
    def query(self, **changes):
        value = {
            "citation_id": "ref-1",
            "title": "Attention Is All You Need",
            "authors": ["Ashish Vaswani", "Noam Shazeer"],
            "year": 2017,
            "identifiers": {"doi": "10.5555/3295222.3295349", "arxiv": "1706.03762"},
        }
        value.update(changes)
        return value

    def provider(self, name: str, status: str, **changes):
        value = {
            "provider": name,
            "status": status,
            "identifier_match": "none",
            "metadata_match": [],
            "evidence_uri": "https://example.org/record",
            "failure_category": "none",
        }
        value.update(changes)
        return value

    def test_exact_identifier_or_two_independent_metadata_matches_verify(self) -> None:
        exact = citation.evaluate_check(
            self.query(),
            [self.provider("crossref", "matched", identifier_match="exact")],
            mode="submission",
        )
        self.assertEqual(exact["overall_status"], "verified")
        self.assertTrue(exact["submission_allowed"])

        corroborated = citation.evaluate_check(
            self.query(identifiers={}),
            [
                self.provider("openalex", "matched", metadata_match=["title", "authors", "year"]),
                self.provider("semantic-scholar", "matched", metadata_match=["title", "authors", "year"]),
            ],
            mode="draft",
        )
        self.assertEqual(corroborated["overall_status"], "verified")

    def test_conflict_wins_and_submission_blocks_non_verified(self) -> None:
        result = citation.evaluate_check(
            self.query(),
            [
                self.provider("crossref", "conflict", identifier_match="different"),
                self.provider("openalex", "matched", metadata_match=["title", "authors", "year"]),
            ],
            mode="submission",
        )
        self.assertEqual(result["overall_status"], "conflict")
        self.assertFalse(result["submission_allowed"])

    def test_timeout_and_429_are_pending_not_fake_or_not_found(self) -> None:
        for category in ("timeout", "rate-limit"):
            with self.subTest(category=category):
                result = citation.evaluate_check(
                    self.query(),
                    [self.provider("crossref", "unavailable", failure_category=category)],
                    mode="submission",
                )
                self.assertEqual(result["overall_status"], "pending")
                self.assertFalse(result["submission_allowed"])

    def test_not_found_requires_completed_queries_and_single_title_match_is_insufficient(self) -> None:
        missing = citation.evaluate_check(
            self.query(),
            [
                self.provider("crossref", "not-found", evidence_uri=""),
                self.provider("arxiv", "not-found", evidence_uri=""),
            ],
        )
        self.assertEqual(missing["overall_status"], "not-found")

        title_only = citation.evaluate_check(
            self.query(identifiers={}),
            [
                self.provider("openalex", "matched", metadata_match=["title"]),
                self.provider("semantic-scholar", "not-found", evidence_uri=""),
            ],
        )
        self.assertEqual(title_only["overall_status"], "not-found")

    def test_reading_scope_and_claim_locations_are_preserved(self) -> None:
        result = citation.evaluate_check(
            self.query(),
            [self.provider("crossref", "matched", identifier_match="exact")],
            reading_scope="full-text",
            claim_locations=[{"claim_id": "claim-1", "page": "12", "section": "Methods"}],
        )
        self.assertEqual(result["reading_scope"], "full-text")
        self.assertEqual(result["claim_locations"][0]["page"], "12")
        citation.validate_check(result)

    def test_batch_envelope_validates_summary(self) -> None:
        verified = citation.evaluate_check(
            self.query(),
            [self.provider("crossref", "matched", identifier_match="exact")],
        )
        batch = citation.build_batch([verified])
        self.assertEqual(batch["schema_version"], "ds-lite.citation-check-batch.v1")
        self.assertEqual(batch["summary"], {"verified": 1, "conflict": 0, "not-found": 0, "pending": 0})
        citation.validate_batch(batch)

    def test_cache_ttl_and_pending_non_reuse(self) -> None:
        cache_root = Path(tempfile.mkdtemp(prefix="ds-lite-citation-cache-"))
        now = datetime(2026, 7, 24, tzinfo=timezone.utc)
        verified = citation.evaluate_check(
            self.query(),
            [self.provider("crossref", "matched", identifier_match="exact")],
            checked_at=now,
        )
        citation.write_cache(cache_root, verified)
        self.assertIsNotNone(citation.read_cache(cache_root, "ref-1", now=now + timedelta(days=29)))
        self.assertIsNone(citation.read_cache(cache_root, "ref-1", now=now + timedelta(days=31)))

        conflict = citation.evaluate_check(
            self.query(citation_id="ref-2"),
            [self.provider("crossref", "conflict", identifier_match="different")],
            checked_at=now,
        )
        citation.write_cache(cache_root, conflict)
        self.assertIsNotNone(citation.read_cache(cache_root, "ref-2", now=now + timedelta(days=6)))
        self.assertIsNone(citation.read_cache(cache_root, "ref-2", now=now + timedelta(days=8)))

        pending = citation.evaluate_check(
            self.query(citation_id="ref-3"),
            [self.provider("crossref", "unavailable", failure_category="timeout")],
            checked_at=now,
        )
        self.assertFalse(citation.write_cache(cache_root, pending))
        self.assertIsNone(citation.read_cache(cache_root, "ref-3", now=now))

    def test_live_acceptance_fails_closed_without_explicit_authorization(self) -> None:
        root = Path(tempfile.mkdtemp(prefix="ds-lite-academic-live-"))
        query_path = root / "query.json"
        receipt_path = root / "receipt.json"
        query_path.write_text(json.dumps(self.query()), encoding="utf-8")
        script = ROOT / "tools" / "validation" / "academic_live_provider_acceptance.py"
        completed = subprocess.run(
            [
                sys.executable,
                str(script),
                "--repo-root",
                str(ROOT),
                "--query",
                str(query_path),
                "--output",
                str(receipt_path),
            ],
            text=True,
            encoding="utf-8",
            capture_output=True,
        )
        self.assertEqual(completed.returncode, 2)
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        self.assertEqual(receipt["status"], "blocked")
        self.assertEqual(receipt["reason"], "external-provider-authorization-required")
        self.assertFalse(receipt["network_attempted"])

    def test_live_acceptance_retries_only_transient_provider_failures(self) -> None:
        root = Path(tempfile.mkdtemp(prefix="ds-lite-academic-retry-"))
        query_path = root / "query.json"
        query_path.write_text(json.dumps(self.query()), encoding="utf-8")
        calls = []

        def query_provider(provider, query, timeout):
            calls.append(provider)
            if len(calls) == 1:
                return self.provider("crossref", "unavailable", evidence_uri="", failure_category="rate-limit")
            return self.provider("crossref", "matched", identifier_match="exact")

        fake_citation = SimpleNamespace(
            CitationCheckError=ValueError,
            query_provider=query_provider,
            evaluate_check=lambda query, results, **_: {
                "overall_status": "verified", "submission_allowed": True, "providers": results,
            },
        )
        args = SimpleNamespace(
            authorized_external_provider=True,
            provider=["crossref"],
            repo_root=str(ROOT),
            core_root=None,
            query=str(query_path),
            reading_scope="metadata-only",
            timeout=1.0,
            max_attempts=3,
        )
        with patch.object(live_acceptance, "_load_module", return_value=fake_citation), \
             patch.object(live_acceptance.time, "sleep") as sleep:
            receipt, code = live_acceptance.run(args)
        self.assertEqual(code, 0)
        self.assertEqual(receipt["request_count"], 2)
        self.assertEqual(receipt["attempts_per_provider"], {"crossref": 2})
        self.assertTrue(receipt["automatic_retry"])
        sleep.assert_called_once_with(1)

    def test_live_acceptance_isolates_transient_exception_and_continues(self) -> None:
        root = Path(tempfile.mkdtemp(prefix="ds-lite-academic-isolation-"))
        query_path = root / "query.json"
        query_path.write_text(json.dumps(self.query()), encoding="utf-8")
        calls = []

        def query_provider(provider, query, timeout):
            calls.append(provider)
            if provider == "crossref":
                raise TimeoutError("private transport detail")
            return self.provider(provider, "matched", identifier_match="exact")

        fake_citation = SimpleNamespace(
            CitationCheckError=ValueError,
            query_provider=query_provider,
            evaluate_check=lambda query, results, **_: {
                "overall_status": "verified", "submission_allowed": True, "providers": results,
            },
        )
        args = SimpleNamespace(
            authorized_external_provider=True,
            provider=["crossref", "openalex"],
            repo_root=str(ROOT),
            core_root=None,
            query=str(query_path),
            reading_scope="metadata-only",
            timeout=1.0,
            max_attempts=1,
        )
        with patch.object(live_acceptance, "_load_module", return_value=fake_citation):
            receipt, code = live_acceptance.run(args)
        self.assertEqual(code, 2)
        self.assertEqual(calls, ["crossref", "openalex"])
        self.assertEqual(receipt["provider_statuses"], {"crossref": "unavailable", "openalex": "matched"})
        self.assertNotIn("private transport detail", json.dumps(receipt))

    def test_live_acceptance_receipt_is_preliminary_and_not_candidate_bound(self) -> None:
        args = SimpleNamespace(authorized_external_provider=False, provider=None)
        receipt = live_acceptance._base(args)
        self.assertEqual(receipt["evidence_stage"], "preliminary")
        self.assertFalse(receipt["candidate_bound"])
        self.assertIsNone(receipt["candidate_digest"])
        self.assertTrue(receipt["sanitized"])
        self.assertFalse(receipt["host_acceptance_substitute"])

    def test_write_fresh_does_not_overwrite_after_stale_absence_check(self) -> None:
        root = Path(tempfile.mkdtemp(prefix="ds-lite-academic-exclusive-"))
        output = root / "receipt.json"
        output.write_text("historical receipt\n", encoding="utf-8")
        with patch.object(Path, "exists", return_value=False):
            with self.assertRaises(live_acceptance.AcceptanceError):
                live_acceptance._write_fresh(output, {"status": "passed"})
        self.assertEqual(output.read_text(encoding="utf-8"), "historical receipt\n")


class RevisionProtocolTests(unittest.TestCase):
    def constraints(self):
        return {
            "schema_version": "ds-lite.revision-constraints.v1",
            "allowed_paths": ["paper/main.tex", "paper/sections/"],
            "allow_new_citations": False,
            "allow_new_numbers": False,
            "allow_new_theorems": False,
            "allow_delete_citations": False,
            "allow_delete_sections": False,
            "max_files_changed": 2,
            "max_operations": 4,
            "approval_refs": [],
            "extensions": {},
        }

    def test_forbidden_path_and_unapproved_semantic_changes_block(self) -> None:
        changes = [
            {"path": "data/results.csv", "operation": "modify", "effects": []},
            {"path": "paper/main.tex", "operation": "modify", "effects": ["new-number"]},
        ]
        result = revision.evaluate_revision(self.constraints(), changes)
        self.assertEqual(result["status"], "blocked")
        self.assertIn("path-out-of-scope", result["violations"])
        self.assertIn("new-number-not-approved", result["violations"])

    def test_approved_new_citation_and_legal_micro_edit_pass(self) -> None:
        constraints = self.constraints()
        constraints["allow_new_citations"] = True
        constraints["approval_refs"] = ["research/approvals/revision-1.md"]
        changes = [
            {"path": "paper/main.tex", "operation": "modify", "effects": ["new-citation"]},
            {"path": "paper/sections/discussion.tex", "operation": "modify", "effects": ["prose-only"]},
        ]
        result = revision.evaluate_revision(constraints, changes)
        self.assertEqual(result["status"], "passed")

    def test_adversarial_review_requires_distinct_fresh_context_receipts(self) -> None:
        observed = revision.build_adversarial_review(
            strongest_objection="The identification assumption is unsupported.",
            attack_receipt={"context_id": "attack-1", "fresh": True},
            adjudicator_receipt={"context_id": "judge-1", "fresh": True},
            concerns=[{"id": "c1", "priority": "P0", "verdict": "sustained"}],
        )
        self.assertEqual(observed["isolation_status"], "observed")
        self.assertEqual(len(observed["strongest_objections"]), 1)

        not_observed = revision.build_adversarial_review(
            strongest_objection="The identification assumption is unsupported.",
            attack_receipt={"context_id": "same", "fresh": True},
            adjudicator_receipt={"context_id": "same", "fresh": True},
            concerns=[],
        )
        self.assertEqual(not_observed["isolation_status"], "not-observed")


if __name__ == "__main__":
    unittest.main()
