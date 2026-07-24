"""Import helpers for the hyphenated plugin source directory used by tests."""
from __future__ import annotations

import importlib.util
from pathlib import Path

_PATH = Path(__file__).parent / "deepscientist-lite" / "scripts" / "ds_lite_loop.py"
_SPEC = importlib.util.spec_from_file_location("ds_lite_loop", _PATH)
if _SPEC is None or _SPEC.loader is None:
    raise ImportError("cannot load ds_lite_loop")
ds_lite_loop = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(ds_lite_loop)
