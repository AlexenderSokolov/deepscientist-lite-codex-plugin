import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from tools.validation import phase5_host_candidate_acceptance as module
from tools.validation.phase5_host_candidate_acceptance import (
    build_fresh_desktop_acceptance,
    build_hook_acceptance,
    write_desktop_witness,
)


DIGEST = "a" * 64


def write(path: Path, value: dict) -> Path:
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


class Phase5HostCandidateAcceptanceTests(unittest.TestCase):
    def candidate(self, root: Path) -> Path:
        return write(root / "candidate.json", {
            "schema_version": "ds-lite.phase5-release-candidate.v1",
            "candidate_digest": DIGEST,
        })

    def test_hook_acceptance_requires_current_core_identity_and_one_turn_repair(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            current = {"source_sha256": "b" * 64, "skill_count": 9,
                       "hook_events": ["PostToolUse", "PreToolUse", "Stop", "UserPromptSubmit"]}
            prep = write(root / "prep.json", {
                "schema_version": "ds-lite.trusted-host-preparation.v1", "status": "prepared",
                "codex_version": "0.146.0", "config_validated": True,
                "workspace_trust_configured": True, "secret_material_persisted": False,
                "candidate": current,
            })
            host = write(root / "host.json", {
                "schema_version": "ds-lite.fresh-host-probe.v1", "status": "passed",
                "failure_layer": "none", "terminal_event_observed": True,
                "event_type_counts": {"thread.started": 1, "turn.started": 1, "turn.completed": 1},
                "raw_output_persisted": False,
                "cli_identity": {"enforced": True, "expected_version": "0.146.0", "sha256_match": True},
                "hook_event_sequence": [
                    {"event_type": "stop", "decision": "block", "reason_present": True, "stop_hook_active": False},
                    {"event_type": "stop", "decision": "allow", "reason_present": True, "stop_hook_active": True},
                ],
            })
            verifier = write(root / "verifier.json", {
                "schema_version": "ds-lite.phase5-hook-continuation-verifier.v1",
                "status": "passed", "release_allowed": False,
                "checks": {name: True for name in (
                    "runtime_pin_enforced", "one_cli_turn", "one_terminal_turn", "terminal_observed",
                    "stop_block_then_allow", "nonempty_stop_reasons", "repair_budget_transition",
                    "same_cli_turn_repair",
                )},
            })
            result = build_hook_acceptance(
                self.candidate(root), prep, host, verifier, current, root / "out.json",
            )
            self.assertEqual(result["schema_version"], "ds-lite.trusted-hook-acceptance.v1")
            self.assertEqual(result["status"], "passed")
            changed = dict(current, source_sha256="c" * 64)
            with self.assertRaisesRegex(ValueError, "Hook"):
                build_hook_acceptance(
                    self.candidate(root), prep, host, verifier, changed, root / "bad.json",
                )

    def test_desktop_witness_is_sanitized_and_requires_every_observation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            provider = write(root / "provider.json", {"status": "passed"})
            required = {
                "candidate_artifact_read", "evidence_pack_sanitized", "fresh_desktop_observed",
                "openscience_task_observed", "provider_receipt_bound", "terminal_observed",
            }
            witness = write_desktop_witness(
                self.candidate(root), provider, "thread-1", "turn-1", required, root / "witness.json",
            )
            self.assertEqual(witness["status"], "passed")
            self.assertEqual(
                witness["schema_version"], "ds-lite.openscience-host-observation.v1",
            )
            self.assertNotIn("thread-1", json.dumps(witness))
            with self.assertRaisesRegex(ValueError, "observations"):
                write_desktop_witness(
                    self.candidate(root), provider, "thread-2", "turn-2",
                    required - {"terminal_observed"}, root / "bad.json",
                )

    def test_fresh_desktop_requires_exact_candidate_cache_hook_and_witness(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            candidate = self.candidate(root)
            packages = dict(module.EXPECTED_PACKAGES)
            cache = write(root / "cache.json", {
                "schema_version": "ds-lite.formal-cache-acceptance.v1", "status": "passed",
                "candidate_digest": DIGEST, "expected_packages": packages,
                "observed_packages": packages, "model_request_made": False,
                "raw_output_persisted": False,
            })
            hook = write(root / "hook.json", {
                "schema_version": "ds-lite.trusted-hook-acceptance.v1", "status": "passed",
                "candidate_digest": DIGEST, "release_allowed": False,
            })
            provider = write(root / "provider.json", {"status": "passed"})
            witness_path = root / "witness.json"
            write_desktop_witness(
                candidate, provider, "thread", "turn", {
                    "candidate_artifact_read", "evidence_pack_sanitized", "fresh_desktop_observed",
                    "openscience_task_observed", "provider_receipt_bound", "terminal_observed",
                }, witness_path,
            )
            result = build_fresh_desktop_acceptance(candidate, cache, hook, witness_path, root / "out.json")
            self.assertEqual(result["status"], "passed")
            self.assertFalse(result["release_allowed"])


if __name__ == "__main__":
    unittest.main()
