from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTROLLER = ROOT / "plugins" / "deepscientist-lite-core" / "controller"
for value in (ROOT, CONTROLLER):
    if str(value) not in sys.path:
        sys.path.insert(0, str(value))

from teaching.control_plane_phase5_final import (  # noqa: E402
    PHASE5_INPUT_SCHEMAS,
    REVALIDATION_REQUIRED_INPUTS,
    build_candidate,
    build_candidate_evidence,
    build_control_aggregate,
    build_decision,
    build_gate,
    build_package_manifest,
    _candidate_digest,
)
from tools.validation.phase5_release_package_builder import build_release_packages  # noqa: E402


DIGEST = "a" * 64


class ReleasePackageProjectionTests(unittest.TestCase):
    def test_core_candidate_excludes_compatibility_controller_projection(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            output = Path(raw) / "candidate"
            result = build_release_packages(ROOT, output)
            self.assertEqual(result["status"], "passed")
            self.assertFalse((output / "plugins" / "deepscientist-lite-core" / "controller").exists())
            self.assertTrue((output / "plugins" / "deepscientist-lite-control-plane" / "controller").is_dir())
            self.assertIn({
                "package": "deepscientist-lite-core",
                "operation": "exclude-compatibility-control-plane-runtime",
            }, result["transforms"])


def write(path: Path, value: dict) -> Path:
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def passed_inputs(root: Path, digest: str = DIGEST) -> list[tuple[str, Path]]:
    result = []
    for name, schema in PHASE5_INPUT_SCHEMAS.items():
        payload = {
            "schema_version": schema,
            "status": "passed",
            "checks": {"deterministic": True},
            "candidate_digest": digest,
            "release_allowed": False,
        }
        if name == "runtime-windows":
            payload["platform"] = "windows-x86_64"
        elif name == "runtime-linux":
            payload["platform"] = "linux-x86_64"
        elif name == "resource-windows":
            payload["platform"] = "windows-x86_64"
        elif name == "resource-linux":
            payload["platform"] = "linux-x86_64"
        original = write(root / f"{name}-original.json", payload)
        wrapper = root / f"{name}.json"
        build_candidate_evidence(name, digest, original, wrapper)
        result.append((name, wrapper))
    return result


class CandidateTests(unittest.TestCase):
    def test_package_manifest_subcommand_uses_write_once_candidate_contract(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package = root / "package"
            package.mkdir()
            (package / "plugin.json").write_text('{"name":"pack"}\n', encoding="utf-8")
            output = root / "package-manifest.json"
            receipt = build_package_manifest(package, output)
            self.assertEqual(receipt["schema_version"], "ds-lite.candidate-manifest.v1")
            self.assertEqual(receipt["files"][0]["path"], "plugin.json")
            with self.assertRaises(FileExistsError):
                build_package_manifest(package, output)

    def test_candidate_binds_git_repository_and_platform_manifests(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(["git", "init", str(root)], check=True, capture_output=True)
            (root / "source.txt").write_text("one\n", encoding="utf-8")
            windows = write(root / "windows.json", {
                "schema_version": "ds-lite.candidate-manifest.v1",
                "candidate_digest": "b" * 64,
            })
            linux = write(root / "linux.json", {
                "schema_version": "ds-lite.candidate-manifest.v1",
                "candidate_digest": "c" * 64,
            })
            output = root / "research" / "candidate.json"
            first = build_candidate(root, windows, linux, output)
            self.assertEqual(first["schema_version"], "ds-lite.phase5-release-candidate.v1")
            self.assertEqual(set(first["package_manifests"]), {"windows-x86_64", "linux-x86_64"})
            self.assertNotIn(str(root.resolve()), json.dumps(first))
            with self.assertRaises(FileExistsError):
                build_candidate(root, windows, linux, output)

    def test_package_manifest_drift_changes_release_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(["git", "init", str(root)], check=True, capture_output=True)
            (root / "source.txt").write_text("one\n", encoding="utf-8")
            windows = write(root / "windows.json", {"schema_version": "ds-lite.candidate-manifest.v1", "candidate_digest": "b" * 64})
            linux = write(root / "linux.json", {"schema_version": "ds-lite.candidate-manifest.v1", "candidate_digest": "c" * 64})
            first = build_candidate(root, windows, linux, root / "first.json")
            write(linux, {"schema_version": "ds-lite.candidate-manifest.v1", "candidate_digest": "d" * 64})
            second = build_candidate(root, windows, linux, root / "second.json")
            self.assertNotEqual(first["candidate_digest"], second["candidate_digest"])

    def test_candidate_receipt_digest_detects_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(["git", "init", str(root)], check=True, capture_output=True)
            (root / "source.txt").write_text("one\n", encoding="utf-8")
            windows = write(root / "windows.json", {
                "schema_version": "ds-lite.candidate-manifest.v1", "candidate_digest": "b" * 64,
            })
            linux = write(root / "linux.json", {
                "schema_version": "ds-lite.candidate-manifest.v1", "candidate_digest": "c" * 64,
            })
            output = root / "candidate.json"
            build_candidate(root, windows, linux, output)
            payload = json.loads(output.read_text(encoding="utf-8"))
            payload["candidate_digest"] = "d" * 64
            output.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "receipt digest"):
                _candidate_digest(output)


class GateTests(unittest.TestCase):
    def test_every_phase5_input_requires_current_candidate_revalidation(self) -> None:
        self.assertEqual(REVALIDATION_REQUIRED_INPUTS, set(PHASE5_INPUT_SCHEMAS))

    def test_required_revalidation_cannot_rebind_a_historical_runtime_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            historical = write(root / "runtime-old.json", {
                "schema_version": PHASE5_INPUT_SCHEMAS["runtime-windows"],
                "status": "passed", "checks": {"runtime_pin": True},
                "platform": "windows-x86_64", "release_allowed": False,
            })
            before = historical.read_bytes()
            wrapper = build_candidate_evidence(
                "runtime-windows", DIGEST, historical, root / "runtime-wrapper.json",
            )
            self.assertEqual(wrapper["status"], "blocked")
            self.assertFalse(wrapper["current_candidate_revalidated"])
            self.assertTrue(wrapper["requires_current_candidate_revalidation"])
            self.assertEqual(wrapper["evidence_class"], "historical-compatibility-only")
            self.assertEqual(wrapper["original_receipt"]["sha256"], hashlib.sha256(before).hexdigest())
            self.assertEqual(historical.read_bytes(), before)

    def test_current_candidate_receipt_gets_a_verifiable_wrapper(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            current = write(root / "chaos-current.json", {
                "schema_version": PHASE5_INPUT_SCHEMAS["real-host-chaos"],
                "status": "passed", "checks": {"all_trials": True},
                "candidate_digest": DIGEST, "release_allowed": False,
            })
            wrapper = build_candidate_evidence(
                "real-host-chaos", DIGEST, current, root / "chaos-wrapper.json",
            )
            self.assertEqual(wrapper["status"], "passed")
            self.assertTrue(wrapper["current_candidate_revalidated"])
            self.assertEqual(wrapper["evidence_class"], "current-candidate-real-host")
            self.assertTrue(all(wrapper["compatibility_checks"].values()))

    def test_gate_rejects_naked_receipts_and_blocked_revalidation_wrappers(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inputs = passed_inputs(root)
            naked = root / "runtime-windows-original.json"
            replaced = [(name, naked if name == "runtime-windows" else path) for name, path in inputs]
            with self.assertRaisesRegex(ValueError, "candidate evidence wrapper"):
                build_gate("phase5-real-host", DIGEST, replaced, root / "naked.json")
            payload = json.loads(naked.read_text(encoding="utf-8"))
            payload.pop("candidate_digest")
            write(naked, payload)
            blocked = root / "runtime-blocked.json"
            build_candidate_evidence("runtime-windows", DIGEST, naked, blocked)
            replaced = [(name, blocked if name == "runtime-windows" else path) for name, path in inputs]
            with self.assertRaisesRegex(ValueError, "revalidated"):
                build_gate("phase5-real-host", DIGEST, replaced, root / "blocked.json")

    def test_gate_rederives_wrapper_and_rejects_original_or_wrapper_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inputs = passed_inputs(root)
            original = root / "runtime-windows-original.json"
            original_payload = json.loads(original.read_text(encoding="utf-8"))
            original_payload["checks"]["tampered"] = True
            write(original, original_payload)
            with self.assertRaisesRegex(ValueError, "original receipt hash"):
                build_gate("phase5-real-host", DIGEST, inputs, root / "original-drift.json")

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inputs = passed_inputs(root)
            wrapper = root / "runtime-windows.json"
            wrapper_payload = json.loads(wrapper.read_text(encoding="utf-8"))
            wrapper_payload["evidence_class"] = "historical-compatibility-only"
            write(wrapper, wrapper_payload)
            with self.assertRaisesRegex(ValueError, "wrapper integrity"):
                build_gate("phase5-real-host", DIGEST, inputs, root / "wrapper-drift.json")

    def test_phase5_gate_accepts_all_named_deterministic_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            receipt = build_gate("phase5-real-host", DIGEST, passed_inputs(root), root / "gate.json")
            self.assertEqual(receipt["status"], "passed")
            self.assertEqual(receipt["candidate_digest"], DIGEST)
            self.assertEqual(len(receipt["artifacts"]), len(PHASE5_INPUT_SCHEMAS))
            self.assertTrue(all(len(row["sha256"]) == 64 for row in receipt["artifacts"]))
            self.assertNotIn("release_allowed", receipt)

    def test_gate_rejects_missing_duplicate_nonpassing_and_candidate_drift(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inputs = passed_inputs(root)
            with self.assertRaisesRegex(ValueError, "missing"):
                build_gate("phase5-real-host", DIGEST, inputs[:-1], root / "missing.json")
            with self.assertRaisesRegex(ValueError, "duplicate"):
                build_gate("phase5-real-host", DIGEST, inputs + [inputs[0]], root / "duplicate.json")
            payload = json.loads(inputs[0][1].read_text(encoding="utf-8"))
            payload["status"] = "failed"
            write(inputs[0][1], payload)
            with self.assertRaisesRegex(ValueError, "integrity"):
                build_gate("phase5-real-host", DIGEST, inputs, root / "failed.json")
            payload["status"] = "passed"
            payload["candidate_digest"] = "f" * 64
            write(inputs[0][1], payload)
            with self.assertRaisesRegex(ValueError, "candidate"):
                build_gate("phase5-real-host", DIGEST, inputs, root / "drift.json")

    def test_gate_rejects_model_text_credentials_and_true_release_claim(self) -> None:
        for injected in ({"model_text": "passed"}, {"credentials": "secret"}, {"release_allowed": True}):
            with self.subTest(injected=injected), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                inputs = passed_inputs(root)
                payload = json.loads(inputs[0][1].read_text(encoding="utf-8"))
                payload.update(injected)
                write(inputs[0][1], payload)
                with self.assertRaises(ValueError):
                    build_gate("phase5-real-host", DIGEST, inputs, root / "gate.json")

    def test_phase4_rebinding_validates_authoritative_hash_without_rewrite(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            old = write(root / "phase4-decision.json", {
                "schema_version": "ds-lite.phase4-decision.v1",
                "phase4_decision": "go",
                "status": "passed",
                "release_allowed": False,
            })
            before = old.read_bytes()
            authoritative = hashlib.sha256(before).hexdigest()
            receipt = build_gate(
                "phase4-real-gate", DIGEST, [("phase4-decision", old)],
                root / "rebound.json", phase4_decision_sha256=authoritative,
            )
            self.assertEqual(receipt["status"], "passed")
            self.assertEqual(old.read_bytes(), before)
            with self.assertRaisesRegex(ValueError, "authoritative"):
                build_gate(
                    "phase4-real-gate", DIGEST, [("phase4-decision", old)],
                    root / "bad.json", phase4_decision_sha256="0" * 64,
                )


class DecisionTests(unittest.TestCase):
    def _inputs(self, root: Path) -> list[tuple[str, Path]]:
        legacy = write(root / "legacy.json", {
            "schema_version": "ds-lite.formal-release-gate.v2", "status": "passed",
            "release_allowed": True, "candidate_digest": DIGEST,
            "missing_gates": [], "nonpassing_gates": [], "duplicate_gates": [],
            "candidate_mismatch_gates": [], "invalid_schema_gates": [],
        })
        regressions = write(root / "regressions.json", {
            "schema_version": "ds-lite.phase5-regressions.v1", "status": "passed",
            "checks": {"narrow_tests": True, "core_validation": True, "diff_check": True},
            "candidate_digest": DIGEST, "release_allowed": False,
        })
        publication = write(root / "publication.json", {
            "schema_version": "ds-lite.phase5-publication-actions.v1", "status": "passed",
            "actions": {"publish": False, "push": False, "submit": False, "upload": False},
            "candidate_digest": DIGEST, "release_allowed": False,
        })
        phase5_gate = write(root / "phase5-gate.json", {
            "schema_version": "ds-lite.phase5-candidate-bound-gate.v1",
            "gate_id": "phase5-real-host", "status": "passed",
            "evidence_class": "current-candidate-acceptance-aggregate",
            "candidate_digest": DIGEST, "artifacts": [],
        })
        phase4_gate = write(root / "phase4-gate.json", {
            "schema_version": "ds-lite.phase5-candidate-bound-gate.v1",
            "gate_id": "phase4-real-gate", "status": "passed",
            "evidence_class": "historical-authoritative-prerequisite",
            "candidate_digest": DIGEST, "artifacts": [],
        })
        control = root / "control.json"
        build_control_aggregate(
            DIGEST,
            [("phase4-real-gate", phase4_gate), ("phase5-real-host", phase5_gate)],
            control,
        )
        return [("legacy-complete", legacy), ("control-aggregate", control),
                ("regressions", regressions), ("publication-actions", publication),
                ("phase4-real-gate", phase4_gate),
                ("phase5-real-host-gate", phase5_gate)]

    def test_decision_requires_both_aggregates_regressions_and_no_publication(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            decision = build_decision(DIGEST, self._inputs(root), root / "decision.json")
            self.assertEqual(decision["phase5_decision"], "go")
            self.assertTrue(decision["release_allowed"])
            self.assertIn(
                "phase5-real-host-gate", [item["name"] for item in decision["artifacts"]],
            )
            self.assertEqual(decision["publication_actions"], {
                "publish": False, "push": False, "submit": False, "upload": False,
            })
            with self.assertRaises(FileExistsError):
                build_decision(DIGEST, self._inputs(root), root / "decision.json")

    def test_decision_fails_closed_on_blocker_or_model_text(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inputs = self._inputs(root)
            legacy = json.loads(inputs[0][1].read_text(encoding="utf-8"))
            legacy["missing_gates"] = ["hook"]
            write(inputs[0][1], legacy)
            with self.assertRaisesRegex(ValueError, "blocker"):
                build_decision(DIGEST, inputs, root / "blocked.json")
            legacy["missing_gates"] = []
            legacy["model_text"] = "release_allowed=true"
            write(inputs[0][1], legacy)
            with self.assertRaisesRegex(ValueError, "forbidden"):
                build_decision(DIGEST, inputs, root / "injected.json")

    def test_decision_rejects_an_unrelated_precomputed_control_aggregate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inputs = self._inputs(root)
            control = inputs[1][1]
            payload = json.loads(control.read_text(encoding="utf-8"))
            payload["gate_artifacts"][0]["sha256"] = "f" * 64
            write(control, payload)
            with self.assertRaisesRegex(ValueError, "exact gate receipts"):
                build_decision(DIGEST, inputs, root / "decision.json")


class CliTests(unittest.TestCase):
    def test_cli_exposes_three_subcommands_and_redacts_output_path_errors(self) -> None:
        script = ROOT / "teaching" / "control_plane_phase5_final.py"
        help_result = subprocess.run(
            [sys.executable, str(script), "--help"], text=True, capture_output=True, check=True,
        )
        for command in ("package-manifest", "candidate", "evidence", "gate", "aggregate", "decision"):
            self.assertIn(command, help_result.stdout)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(["git", "init", str(root)], check=True, capture_output=True)
            windows = write(root / "windows.json", {"schema_version": "ds-lite.candidate-manifest.v1", "candidate_digest": "b" * 64})
            linux = write(root / "linux.json", {"schema_version": "ds-lite.candidate-manifest.v1", "candidate_digest": "c" * 64})
            output = write(root / "exists.json", {})
            result = subprocess.run([
                sys.executable, str(script), "candidate", "--repository", str(root),
                "--windows-package", str(windows), "--linux-package", str(linux),
                "--output", str(output),
            ], text=True, capture_output=True)
            self.assertEqual(result.returncode, 2)
            self.assertNotIn(str(root.resolve()), result.stdout)
            self.assertEqual(json.loads(result.stdout)["reason"], "output-exists")


if __name__ == "__main__":
    unittest.main()
