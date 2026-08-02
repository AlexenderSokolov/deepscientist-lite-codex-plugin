"""Import helpers for the hyphenated plugin source directory used by tests."""
from __future__ import annotations

import importlib.util
from pathlib import Path

_PATH = Path(__file__).parent / "deepscientist-lite-core" / "scripts" / "ds_lite_loop.py"
_SPEC = importlib.util.spec_from_file_location("ds_lite_loop", _PATH)
if _SPEC is None or _SPEC.loader is None:
    raise ImportError("cannot load ds_lite_loop")
ds_lite_loop = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(ds_lite_loop)

_AUTONOMY_PATH = Path(__file__).parent / "deepscientist-lite-core" / "scripts" / "ds_lite_autonomy.py"
_RECOVERY_PATH = Path(__file__).parent / "deepscientist-lite-core" / "scripts" / "ds_lite_recovery.py"
_RECOVERY_SPEC = importlib.util.spec_from_file_location("ds_lite_recovery", _RECOVERY_PATH)
if _RECOVERY_SPEC is None or _RECOVERY_SPEC.loader is None:
    raise ImportError("cannot load ds_lite_recovery")
ds_lite_recovery = importlib.util.module_from_spec(_RECOVERY_SPEC)
import sys
sys.modules["ds_lite_recovery"] = ds_lite_recovery
_RECOVERY_SPEC.loader.exec_module(ds_lite_recovery)
_AUTONOMY_SPEC = importlib.util.spec_from_file_location("ds_lite_autonomy", _AUTONOMY_PATH)
if _AUTONOMY_SPEC is None or _AUTONOMY_SPEC.loader is None:
    raise ImportError("cannot load ds_lite_autonomy")
ds_lite_autonomy = importlib.util.module_from_spec(_AUTONOMY_SPEC)
_AUTONOMY_SPEC.loader.exec_module(ds_lite_autonomy)

_AUTORESEARCH_PATH = Path(__file__).parent / "deepscientist-lite-core" / "scripts" / "ds_lite_autoresearch_runner.py"
_AUTORESEARCH_SPEC = importlib.util.spec_from_file_location("ds_lite_autoresearch_runner", _AUTORESEARCH_PATH)
if _AUTORESEARCH_SPEC is None or _AUTORESEARCH_SPEC.loader is None:
    raise ImportError("cannot load ds_lite_autoresearch_runner")
ds_lite_autoresearch_runner = importlib.util.module_from_spec(_AUTORESEARCH_SPEC)
_AUTORESEARCH_SPEC.loader.exec_module(ds_lite_autoresearch_runner)
