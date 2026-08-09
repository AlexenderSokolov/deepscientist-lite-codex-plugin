#!/usr/bin/env python3
"""Single entry point for the active DS Lite beta.3 local validation flow."""
from __future__ import annotations

import argparse
import py_compile
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.validation.runtime_identity_check import check_runtime_identity


SKIP_PARTS = {
    "__pycache__",
    ".git",
    "node_modules",
    "vendor",
    ".validation-tmp",
    # This preserved upstream corpus is emitted only in academic-examples.zip.
    "figures4papers",
}


def active_python_files(root: Path) -> list[Path]:
    package_names = (
        "deepscientist-lite-core", "deepscientist-lite-academic", "deepscientist-lite-web",
        "deepscientist-lite-knowledge", "deepscientist-lite-empirical", "deepscientist-lite-engineering",
        "deepscientist-lite-control-plane",
    )
    roots = [*(root / "plugins" / name for name in package_names), root / "tools" / "validation", root / "teaching", root / "tests"]
    return sorted(path for base in roots for path in base.rglob("*.py") if not (set(path.parts) & SKIP_PARTS))


def run(command: list[str], root: Path) -> None:
    completed = subprocess.run(command, cwd=root, check=False)
    if completed.returncode:
        raise SystemExit(completed.returncode)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=str(REPO_ROOT), type=Path)
    parser.add_argument("--skip-tests", action="store_true")
    args = parser.parse_args(argv)
    root = args.repo_root.resolve()
    if not args.skip_tests:
        run([sys.executable, "tests/run_unittest.py"], root)
    run([sys.executable, "tools/validation/release_identity.py", "--check", "--repo-root", str(root)], root)
    run([sys.executable, "tools/validation/generate_academic_contract.py", "--check", "--repo-root", str(root)], root)
    run([sys.executable, "tools/validation/validate_repo.py"], root)
    runtime_issues = check_runtime_identity(root)
    if runtime_issues:
        raise SystemExit("active runtime identity check failed: " + ", ".join(runtime_issues))
    for path in active_python_files(root):
        py_compile.compile(str(path), doraise=True)
    run([sys.executable, "tools/validation/check_cross_system.py", "."], root)
    print("{\"schema_version\":\"ds-lite.validation-all.v1\",\"status\":\"passed\"}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
