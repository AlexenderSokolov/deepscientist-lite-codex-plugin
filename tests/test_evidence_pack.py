from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_SCRIPT = REPO_ROOT / "plugins" / "deepscientist-lite" / "scripts" / "ds_lite_evidence.py"


def run_evidence(root: Path, command: str, *args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    merged = os.environ.copy()
    merged["PYTHONUTF8"] = "1"
    if env:
        merged.update(env)
    return subprocess.run(
        [sys.executable, str(EVIDENCE_SCRIPT), command, "--root", str(root), *args],
        cwd=REPO_ROOT,
        text=True,
        encoding="utf-8",
        capture_output=True,
        env=merged,
    )


def parsed(result: subprocess.CompletedProcess[str]) -> dict:
    text = result.stdout if result.stdout.strip() else result.stderr
    return json.loads(text)


class EvidencePackTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="ds evidence 中文 "))
        (self.root / "research" / "results").mkdir(parents=True)
        (self.root / "inputs").mkdir(parents=True)
        (self.root / "inputs" / "data.txt").write_text("input\n", encoding="utf-8")
        self.contract_path = self.root / "contract input.json"
        self.stdout_path = self.root / "stdout source.log"
        self.stderr_path = self.root / "stderr source.log"
        self.metrics_path = self.root / "metrics source.json"
        self.environment_path = self.root / "environment source.json"
        self.output_path = self.root / "research" / "results" / "result.json"
        self.stdout_path.write_text("训练完成\n", encoding="utf-8")
        self.stderr_path.write_text("", encoding="utf-8")
        self.metrics_path.write_text('{"accuracy": 0.9}\n', encoding="utf-8")
        self.environment_path.write_text(
            json.dumps(
                {
                    "schema_version": "ds-lite.environment.v1",
                    "python": sys.version.split()[0],
                    "platform": sys.platform,
                    "packages": [],
                    "container": "not-applicable",
                    "hardware": "test",
                    "notes": "sanitized",
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        self.output_path.write_text('{"ok": true}\n', encoding="utf-8")
        self.write_contract()

    def contract(self, **updates: object) -> dict:
        payload = {
            "schema_version": "ds-lite.experiment-contract.v1",
            "run_id": "run-01",
            "node_id": "experiment-one",
            "hypothesis": "中文假设可以被可靠记录。",
            "command": "python run_experiment.py",
            "cwd": ".",
            "inputs": ["inputs/data.txt"],
            "metrics": [{"name": "accuracy", "direction": "max", "threshold": 0.8}],
            "seeds": [0, 1],
            "budget": {"value": 2, "unit": "runs"},
            "expected_outputs": ["research/results/result.json"],
            "failure_interpretation": "低于阈值时回滚到基线。",
        }
        payload.update(updates)
        return payload

    def write_contract(self, **updates: object) -> None:
        self.contract_path.write_text(
            json.dumps(self.contract(**updates), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    def initialize(self) -> subprocess.CompletedProcess[str]:
        return run_evidence(
            self.root,
            "init",
            "--run-id",
            "run-01",
            "--contract",
            str(self.contract_path),
        )

    def finalize(self, *extra: str, exit_code: int = 0) -> subprocess.CompletedProcess[str]:
        return run_evidence(
            self.root,
            "finalize",
            "--run-id",
            "run-01",
            "--exit-code",
            str(exit_code),
            "--stdout",
            str(self.stdout_path),
            "--stderr",
            str(self.stderr_path),
            "--metrics",
            str(self.metrics_path),
            "--environment",
            str(self.environment_path),
            "--output",
            "research/results/result.json",
            *extra,
        )

    def manifest(self) -> dict:
        return json.loads(
            (self.root / "research" / "evidence" / "run-01" / "manifest.json").read_text(encoding="utf-8")
        )

    def test_unicode_space_path_finalize_and_verify(self) -> None:
        initialized = self.initialize()
        self.assertEqual(initialized.returncode, 0, initialized.stderr)
        finalized = self.finalize()
        self.assertEqual(finalized.returncode, 0, finalized.stderr)
        verified = run_evidence(self.root, "verify", "--run-id", "run-01", "--strict")
        self.assertEqual(verified.returncode, 0, verified.stdout + verified.stderr)
        manifest = self.manifest()
        self.assertEqual(manifest["verification"]["status"], "pass")
        self.assertNotIn(str(self.root), json.dumps(manifest, ensure_ascii=False))
        output_record = next(record for record in manifest["files"] if record["role"] == "output")
        input_record = next(record for record in manifest["files"] if record["role"] == "input")
        expected_hash = hashlib.sha256(self.output_path.read_bytes()).hexdigest()
        self.assertEqual(output_record["sha256"], expected_hash)
        self.assertEqual(input_record["sha256"], hashlib.sha256((self.root / "inputs" / "data.txt").read_bytes()).hexdigest())

    def test_tampering_is_detected(self) -> None:
        self.assertEqual(self.initialize().returncode, 0)
        self.assertEqual(self.finalize().returncode, 0)
        packed_stdout = self.root / "research" / "evidence" / "run-01" / "stdout.log"
        packed_stdout.write_text("tampered\n", encoding="utf-8")
        result = run_evidence(self.root, "verify", "--run-id", "run-01")
        self.assertEqual(result.returncode, 1)
        self.assertTrue(any("hash changed" in item for item in parsed(result)["errors"]))

    def test_missing_log_rejects_finalize(self) -> None:
        self.assertEqual(self.initialize().returncode, 0)
        missing = self.root / "missing.log"
        result = run_evidence(
            self.root,
            "finalize",
            "--run-id",
            "run-01",
            "--exit-code",
            "0",
            "--stdout",
            str(missing),
            "--stderr",
            str(self.stderr_path),
            "--metrics",
            str(self.metrics_path),
            "--environment",
            str(self.environment_path),
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("does not exist", result.stderr)

    def test_failed_process_remains_valid_evidence(self) -> None:
        self.write_contract(
            metrics=[{"name": "accuracy", "direction": "observe"}],
            expected_outputs=[],
        )
        self.assertEqual(self.initialize().returncode, 0)
        self.assertEqual(self.finalize(exit_code=7).returncode, 0)
        result = run_evidence(self.root, "verify", "--run-id", "run-01", "--strict")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.manifest()["status"], "failed")

    def test_repeated_finalize_is_idempotent(self) -> None:
        self.assertEqual(self.initialize().returncode, 0)
        first = self.finalize()
        second = self.finalize()
        self.assertTrue(parsed(first)["changed"])
        self.assertFalse(parsed(second)["changed"])

    def test_repeated_init_without_created_at_is_idempotent(self) -> None:
        first = self.initialize()
        second = self.initialize()
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertTrue(parsed(first)["created"])
        self.assertFalse(parsed(second)["created"])

    def test_sensitive_contract_and_environment_fields_are_rejected(self) -> None:
        self.write_contract(api_key="do-not-store")
        contract_result = self.initialize()
        self.assertEqual(contract_result.returncode, 1)
        self.assertIn("unsupported fields", contract_result.stderr)
        self.write_contract()
        self.assertEqual(self.initialize().returncode, 0)
        self.environment_path.write_text(
            '{"schema_version":"ds-lite.environment.v1","token":"secret"}\n', encoding="utf-8"
        )
        environment_result = self.finalize()
        self.assertEqual(environment_result.returncode, 1)
        self.assertIn("unsupported fields", environment_result.stderr)

    def test_external_output_requires_explicit_hashing(self) -> None:
        external_root = Path(tempfile.mkdtemp(prefix="ds evidence external "))
        external_file = external_root / "result.json"
        external_file.write_text('{"score": 1}\n', encoding="utf-8")
        self.write_contract(expected_outputs=["external://data/result.json"])
        self.assertEqual(self.initialize().returncode, 0)
        base_args = [
            "--run-id",
            "run-01",
            "--exit-code",
            "0",
            "--stdout",
            str(self.stdout_path),
            "--stderr",
            str(self.stderr_path),
            "--metrics",
            str(self.metrics_path),
            "--environment",
            str(self.environment_path),
            "--output",
            "external://data/result.json",
        ]
        env = {"DS_LITE_EXTERNAL_DATA": str(external_root)}
        finalized = run_evidence(self.root, "finalize", *base_args, env=env)
        self.assertEqual(finalized.returncode, 0, finalized.stderr)
        self.assertNotIn(str(external_root), json.dumps(self.manifest(), ensure_ascii=False))
        strict = run_evidence(self.root, "verify", "--run-id", "run-01", "--strict", env=env)
        self.assertEqual(strict.returncode, 1)
        self.assertIn("without a hash", strict.stdout)
        hashed = run_evidence(self.root, "finalize", *base_args, "--hash-external", env=env)
        self.assertEqual(hashed.returncode, 0, hashed.stderr)
        verified = run_evidence(self.root, "verify", "--run-id", "run-01", "--strict", env=env)
        self.assertEqual(verified.returncode, 0, verified.stdout + verified.stderr)

    def test_absolute_contract_path_is_rejected(self) -> None:
        self.write_contract(inputs=[str((self.root / "inputs" / "data.txt").resolve())])
        result = self.initialize()
        self.assertEqual(result.returncode, 1)
        self.assertIn("absolute paths are forbidden", result.stderr)


if __name__ == "__main__":
    unittest.main()
