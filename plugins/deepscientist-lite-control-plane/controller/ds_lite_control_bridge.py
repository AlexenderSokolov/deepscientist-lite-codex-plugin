"""Runtime boundary for the optional DS Lite control-plane package.

The copied controller under this package is canonical. The historical Core
controller remains a one-beta compatibility projection and is never selected
unless a caller explicitly asks for it.
"""
from __future__ import annotations

import sys
from pathlib import Path


def canonical_controller_root() -> Path:
    return Path(__file__).resolve().parent


def core_controller_root() -> Path:
    """Return the historical Core projection for migration diagnostics."""
    return Path(__file__).resolve().parents[2] / "deepscientist-lite-core" / "controller"


def load_core_controller() -> Path:
    root = canonical_controller_root()
    if not root.is_dir():
        raise RuntimeError("control-plane canonical controller is missing")
    value = str(root)
    if value not in sys.path:
        sys.path.insert(0, value)
    return root


def load_compatibility_controller() -> Path:
    root = core_controller_root()
    if not root.is_dir():
        raise RuntimeError("historical Core controller projection is missing")
    return root
