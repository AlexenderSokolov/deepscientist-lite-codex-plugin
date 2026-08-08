from __future__ import annotations

import hashlib
import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CANONICAL = ROOT / "plugins" / "deepscientist-lite-control-plane" / "controller"
COMPATIBILITY = ROOT / "plugins" / "deepscientist-lite-core" / "controller"
BRIDGE = CANONICAL / "ds_lite_control_bridge.py"


def runtime_files(root: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file() or "__pycache__" in path.parts:
            continue
        relative = path.relative_to(root).as_posix()
        result[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


class ControlPlaneRuntimeBoundaryTests(unittest.TestCase):
    def test_control_plane_bundles_the_canonical_controller_runtime(self) -> None:
        self.assertTrue((CANONICAL / "ds_lite_control" / "app_server.py").is_file())
        self.assertTrue((CANONICAL / "ds_lite_control" / "dbos_bridge.py").is_file())
        self.assertEqual(runtime_files(CANONICAL), runtime_files(COMPATIBILITY) | {
            "ds_lite_control_bridge.py": hashlib.sha256(BRIDGE.read_bytes()).hexdigest(),
        })

    def test_bridge_selects_canonical_runtime_before_legacy_projection(self) -> None:
        spec = importlib.util.spec_from_file_location("control_plane_bridge", BRIDGE)
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        selected = module.load_core_controller()
        self.assertEqual(selected, CANONICAL)
        self.assertEqual(module.load_compatibility_controller(), COMPATIBILITY)
        self.assertEqual(sys.path[0], str(CANONICAL))


if __name__ == "__main__":
    unittest.main()
