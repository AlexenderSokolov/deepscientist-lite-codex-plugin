from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.validation import openscience_candidate_acceptance as acceptance


DIGEST = "a" * 64
PROVIDERS = ("crossref", "openalex", "semantic-scholar", "arxiv")


def write(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def provider_payload(**changes) -> dict:
    payload = {
        "schema_version": "ds-lite.academic-provider-acceptance.v1",
        "status": "passed",
        "reason": "authorized-live-providers-observed",
        "evidence_stage": "preliminary",
        "candidate_bound": False,
        "candidate_digest": None,
        "sanitized": True,
        "host_acceptance_substitute": False,
        "authorized_external_provider": True,
        "network_attempted": True,
        "providers": list(PROVIDERS),
        "provider_statuses": {name: "matched" for name in PROVIDERS},
        "unverified_items": [],
    }
    payload.update(changes)
    return payload


def host_payload(provider_path: Path, **changes) -> dict:
    payload = {
        "schema_version": "ds-lite.openscience-host-observation.v1",
        "status": "passed",
        "candidate_digest": DIGEST,
        "fresh_identity": True,
        "terminal_status": "completed",
        "host_surface": "fresh-desktop-openscience",
        "provider_receipt_sha256": hashlib.sha256(provider_path.read_bytes()).hexdigest(),
        "sanitized": True,
        "checks": {
            "fresh_desktop_observed": True,
            "openscience_task_observed": True,
            "terminal_observed": True,
        },
    }
    payload.update(changes)
    return payload


class OpenScienceCandidateAcceptanceTests(unittest.TestCase):
    def test_passes_only_with_all_providers_and_independent_fresh_host(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            provider = write(root / "provider.json", provider_payload())
            host = write(root / "host.json", host_payload(provider))
            output = root / "acceptance.json"
            receipt = acceptance.build_acceptance(DIGEST, provider, host, output)
            self.assertEqual(receipt["schema_version"], "ds-lite.openscience-acceptance.v1")
            self.assertEqual(receipt["status"], "passed")
            self.assertEqual(receipt["candidate_digest"], DIGEST)
            self.assertTrue(all(receipt["checks"].values()))
            self.assertFalse(receipt["provider_probe_substituted_for_host"])
            self.assertFalse(receipt["release_allowed"])

    def test_provider_probe_cannot_substitute_for_host_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            provider = write(root / "provider.json", provider_payload())
            receipt = acceptance.build_acceptance(
                DIGEST, provider, provider, root / "acceptance.json",
            )
            self.assertEqual(receipt["status"], "blocked")
            self.assertFalse(receipt["checks"]["independent_fresh_host_receipt"])
            self.assertFalse(receipt["provider_probe_substituted_for_host"])

    def test_unavailable_provider_keeps_acceptance_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            statuses = {name: "matched" for name in PROVIDERS}
            statuses["semantic-scholar"] = "unavailable"
            provider = write(root / "provider.json", provider_payload(
                status="blocked", provider_statuses=statuses,
                unverified_items=["provider:semantic-scholar"],
            ))
            host = write(root / "host.json", host_payload(provider))
            receipt = acceptance.build_acceptance(DIGEST, provider, host, root / "acceptance.json")
            self.assertEqual(receipt["status"], "blocked")
            self.assertFalse(receipt["checks"]["all_providers_available"])

    def test_malformed_provider_status_is_blocked_instead_of_crashing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            statuses = {name: "matched" for name in PROVIDERS}
            statuses["crossref"] = []
            provider = write(root / "provider.json", provider_payload(provider_statuses=statuses))
            host = write(root / "host.json", host_payload(provider))
            receipt = acceptance.build_acceptance(DIGEST, provider, host, root / "acceptance.json")
            self.assertEqual(receipt["status"], "blocked")
            self.assertFalse(receipt["checks"]["all_providers_available"])

    def test_historical_incomplete_or_candidate_drift_is_blocked(self) -> None:
        cases = (
            ("historical-provider", {"evidence_stage": "historical"}, {}),
            ("nonterminal-host", {}, {"terminal_status": "running"}),
            ("stale-host", {}, {"fresh_identity": False}),
            ("candidate-drift", {}, {"candidate_digest": "b" * 64}),
        )
        for name, provider_changes, host_changes in cases:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                provider = write(root / "provider.json", provider_payload(**provider_changes))
                host = write(root / "host.json", host_payload(provider, **host_changes))
                receipt = acceptance.build_acceptance(DIGEST, provider, host, root / "acceptance.json")
                self.assertEqual(receipt["status"], "blocked")

    def test_candidate_digest_is_required(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            provider = write(root / "provider.json", provider_payload())
            host = write(root / "host.json", host_payload(provider))
            with self.assertRaisesRegex(ValueError, "candidate digest"):
                acceptance.build_acceptance("", provider, host, root / "acceptance.json")
            self.assertFalse((root / "acceptance.json").exists())

    def test_sensitive_fields_and_private_absolute_paths_are_rejected(self) -> None:
        injections = (
            {"credentials": "secret"},
            {"raw_stderr": "private output"},
            {"environment": {"TOKEN": "secret"}},
            {"hidden_reasoning": "private"},
            {"artifact_path": r"C:\\Users\\private\\receipt.json"},
        )
        for injection in injections:
            with self.subTest(injection=injection), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                payload = provider_payload()
                payload.update(injection)
                provider = write(root / "provider.json", payload)
                host = write(root / "host.json", host_payload(provider))
                with self.assertRaisesRegex(ValueError, "sensitive"):
                    acceptance.build_acceptance(DIGEST, provider, host, root / "acceptance.json")
                self.assertFalse((root / "acceptance.json").exists())

    def test_output_is_write_once_and_fsynced(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            provider = write(root / "provider.json", provider_payload())
            host = write(root / "host.json", host_payload(provider))
            output = root / "acceptance.json"
            with patch.object(acceptance.os, "fsync") as fsync:
                acceptance.build_acceptance(DIGEST, provider, host, output)
            fsync.assert_called_once()
            before = output.read_bytes()
            with self.assertRaises(FileExistsError):
                acceptance.build_acceptance(DIGEST, provider, host, output)
            self.assertEqual(output.read_bytes(), before)

    def test_input_drift_during_assembly_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            provider = write(root / "provider.json", provider_payload())
            host = write(root / "host.json", host_payload(provider))
            output = root / "acceptance.json"
            original_sha256 = acceptance._sha256
            calls = 0

            def drifting_sha256(path):
                nonlocal calls
                if Path(path).resolve() == provider.resolve():
                    calls += 1
                    if calls == 1:
                        provider.write_text(json.dumps(provider_payload(status="blocked")), encoding="utf-8")
                return original_sha256(path)

            with patch.object(acceptance, "_sha256", side_effect=drifting_sha256):
                with self.assertRaisesRegex(ValueError, "changed during acceptance"):
                    acceptance.build_acceptance(DIGEST, provider, host, output)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
