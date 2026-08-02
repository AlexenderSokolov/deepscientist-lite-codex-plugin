#!/usr/bin/env python3
"""Run the unittest suite with the project-volume tempfile policy installed."""

from __future__ import annotations

import sys
import unittest
import argparse
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.validation.project_temp import install_tempfile_policy


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pattern", default="test*.py")
    args = parser.parse_args()
    install_tempfile_policy(REPO_ROOT)
    suite = unittest.defaultTestLoader.discover(str(REPO_ROOT / "tests"), pattern=args.pattern)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
