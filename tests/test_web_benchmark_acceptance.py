import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "validation" / "web_benchmark_acceptance.py"
TEMP_ROOT = ROOT / "research" / ".validation-tmp" / "test-web-benchmark"
SPEC = importlib.util.spec_from_file_location("web_benchmark_acceptance", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


class WebBenchmarkAcceptanceTests(unittest.TestCase):
    def sandbox(self) -> Path:
        TEMP_ROOT.mkdir(parents=True, exist_ok=True)
        return Path(tempfile.mkdtemp(prefix="case-", dir=TEMP_ROOT))

    def write_source(self, root: Path, name: str, content_hash: str, *, backend="stdlib-http", status="captured") -> Path:
        path = root / f"{name}.json"
        path.write_text(json.dumps({"schema_version": "ds-lite.source-record.v2", "status": status, "content_sha256": content_hash,
                                    "backend_id": backend, "policy": MODULE.POLICY}), encoding="utf-8")
        return path

    def write_failure(self, root: Path, name: str) -> Path:
        path = root / f"{name}.json"
        path.write_text(json.dumps({"schema_version": "ds-lite.web-failure-observation.v1", "status": "observed", "failure_layer": "policy", "policy": MODULE.POLICY}), encoding="utf-8")
        return path

    def test_requires_all_independent_cases_and_adapter(self) -> None:
        root = self.sandbox()
        result, code = MODULE.evaluate([], None)
        self.assertEqual(code, 2)
        self.assertEqual(result["status"], "blocked")
        cases = []
        for name in MODULE.SUCCESS_CASES:
            cases.append(f"{name}={self.write_source(root, name, 'a' * 64)}")
        cases.extend([f"duplicate-url={self.write_source(root, 'dup_a', 'b' * 64)}", f"duplicate-url={self.write_source(root, 'dup_b', 'b' * 64)}"])
        cases.extend([f"changed-content={self.write_source(root, 'changed_a', 'c' * 64)}", f"changed-content={self.write_source(root, 'changed_b', 'd' * 64)}"])
        cases.append(f"timeout={self.write_source(root, 'timeout', '', status='failed')}")
        cases.append(f"access-refused={self.write_source(root, 'access-refused', '', status='failed')}")
        cases.append(f"illegal-url={self.write_failure(root, 'illegal-url')}")
        result, code = MODULE.evaluate(cases, str(self.write_source(root, "adapter", "e" * 64, backend="opencli-cli")))
        self.assertEqual(code, 0)
        self.assertEqual(result["status"], "passed")

    def test_rejects_wrong_duplicate_relation(self) -> None:
        root = self.sandbox()
        a = self.write_source(root, "a", "a" * 64)
        b = self.write_source(root, "b", "b" * 64)
        result, code = MODULE.evaluate([f"duplicate-url={a}", f"duplicate-url={b}"], None)
        self.assertEqual(code, 2)
        self.assertEqual(result["cases"]["duplicate-url"]["status"], "blocked")


if __name__ == "__main__":
    unittest.main()
