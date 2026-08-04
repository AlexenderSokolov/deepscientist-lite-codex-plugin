#!/usr/bin/env python3
"""Cross-platform entry point for DS Lite hooks.

Resolves the Python interpreter at runtime instead of hardcoding "python".
Priority:
  1. DS_LITE_PYTHON environment variable
  2. PYTHON_BIN environment variable
  3. sys.executable (the interpreter running this script)
  4. "python" as a last resort fallback
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def resolve_python() -> str:
    """Return the Python interpreter path to use for hook scripts."""
    for var in ("DS_LITE_PYTHON", "PYTHON_BIN"):
        candidate = os.environ.get(var, "").strip()
        if candidate and Path(candidate).exists():
            return candidate
        if candidate:
            return candidate
    if sys.executable:
        return sys.executable
    return "python"


def main() -> int:
    python_bin = resolve_python()
    hook_script = Path(__file__).parent / "ds_lite_hook.py"
    args = sys.argv[1:]
    cmd = [python_bin, str(hook_script)] + args
    import subprocess
    result = subprocess.run(cmd)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
