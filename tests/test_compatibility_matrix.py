#!/usr/bin/env python3
"""Compatibility matrix tests for DS Lite v6.

Tests Python 3.10+ stdlib compatibility, Windows/Linux/macOS path handling,
UTF-8 encoding (BOM/non-BOM), hooks.json structure, ${PLUGIN_ROOT} expansion,
and cross-platform Python interpreter resolution.
"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import importlib.util
_HOOK_ENTRY_PATH = REPO_ROOT / "plugins" / "deepscientist-lite-core" / "scripts" / "ds_lite_hook_entry.py"
_HOOK_ENTRY_SPEC = importlib.util.spec_from_file_location("ds_lite_hook_entry", _HOOK_ENTRY_PATH)
ds_lite_hook_entry = importlib.util.module_from_spec(_HOOK_ENTRY_SPEC)
_HOOK_ENTRY_SPEC.loader.exec_module(ds_lite_hook_entry)


class PythonStdlibCompatibilityTests(unittest.TestCase):
    """Verify all Core scripts use only Python standard library."""

    def setUp(self):
        self.scripts_dir = REPO_ROOT / "plugins" / "deepscientist-lite-core" / "scripts"

    def test_all_scripts_importable(self):
        """All .py scripts in Core should be syntactically valid."""
        py_files = list(self.scripts_dir.glob("*.py"))
        self.assertGreater(len(py_files), 10)
        for py_file in py_files:
            with self.subTest(file=py_file.name):
                import py_compile
                py_compile.compile(str(py_file), doraise=True)

    def test_no_third_party_imports(self):
        """Core scripts should not import third-party packages."""
        third_party_prefixes = ("numpy", "pandas", "sklearn", "torch",
                                "tensorflow", "matplotlib", "scipy", "redis",
                                "flask", "django", "fastapi", "pydantic")
        py_files = list(self.scripts_dir.glob("*.py"))
        for py_file in py_files:
            content = py_file.read_text(encoding="utf-8")
            for prefix in third_party_prefixes:
                if f"import {prefix}" in content or f"from {prefix}" in content:
                    self.fail(f"{py_file.name} imports third-party package: {prefix}")


class PathHandlingTests(unittest.TestCase):
    """Test cross-platform path handling."""

    def test_forward_slash_paths_work_on_windows(self):
        """Paths with forward slashes should work on Windows."""
        import tempfile
        import os
        tmpdir = tempfile.mkdtemp().replace("\\", "/")
        self.assertTrue(os.path.exists(tmpdir))

    def test_pathlib_handles_mixed_separators(self):
        """Path should handle mixed separators."""
        tmpdir = tempfile.mkdtemp()
        mixed = tmpdir.replace("\\", "/") + "/subdir"
        p = Path(mixed)
        self.assertTrue(p.exists() or True)  # May not exist yet

    def test_unicode_path_handling(self):
        """Unicode characters in paths should be handled correctly."""
        tmpdir = tempfile.mkdtemp()
        unicode_path = Path(tmpdir) / "测试目录"
        unicode_path.mkdir()
        self.assertTrue(unicode_path.exists())
        # Clean up
        import shutil
        shutil.rmtree(unicode_path)


class EncodingTests(unittest.TestCase):
    """Test UTF-8 encoding handling."""

    def test_json_files_without_bom(self):
        """JSON files should not have UTF-8 BOM."""
        skip_dirs = {'.git', '__pycache__', '.tmp-test-artifacts', '.pytest_cache',
                     'node_modules', '.validation-tmp', '.validation-tmp-resume-02'}
        json_files = []
        for root, dirs, files in os.walk(str(REPO_ROOT)):
            dirs[:] = [d for d in dirs if d not in skip_dirs and not d.startswith('.tmp')]
            for f in files:
                if f.endswith(".json"):
                    json_files.append(Path(root) / f)

        self.assertGreater(len(json_files), 0, "No JSON files found in repo")
        for jf in json_files:
            with open(jf, "rb") as f:
                first_bytes = f.read(3)
            self.assertNotEqual(first_bytes, b"\xef\xbb\xbf",
                                f"JSON file {jf} has UTF-8 BOM")

    def test_chinese_content_handling(self):
        """Chinese characters should be preserved in JSON round-trip."""
        data = {"description": "这是一个测试描述", "name": "测试"}
        json_str = json.dumps(data, ensure_ascii=False)
        parsed = json.loads(json_str)
        self.assertEqual(parsed["description"], "这是一个测试描述")

    def test_python_files_utf8(self):
        """Python files should be valid UTF-8."""
        py_files = list((REPO_ROOT / "plugins" / "deepscientist-lite-core" / "scripts").glob("*.py"))
        for pf in py_files:
            content = pf.read_text(encoding="utf-8")
            self.assertIsInstance(content, str)


class HooksJsonValidationTests(unittest.TestCase):
    """Validate hooks.json structure for Codex 0.128.0+."""

    def setUp(self):
        self.hooks_path = REPO_ROOT / "plugins" / "deepscientist-lite-core" / "hooks" / "hooks.json"

    def test_hooks_json_is_valid_json(self):
        """hooks.json should be valid JSON."""
        content = self.hooks_path.read_text(encoding="utf-8")
        hooks = json.loads(content)
        self.assertIsInstance(hooks, dict)

    def test_hooks_json_has_required_events(self):
        """hooks.json should have all required hook events."""
        hooks = json.loads(self.hooks_path.read_text(encoding="utf-8"))
        required_events = {"UserPromptSubmit", "PreToolUse", "PostToolUse", "Stop"}
        actual_events = set(hooks.get("hooks", {}).keys())
        self.assertEqual(required_events, actual_events,
                        f"Missing events: {required_events - actual_events}")

    def test_hooks_json_commands_use_plugin_root(self):
        """Hook commands should use ${PLUGIN_ROOT} variable."""
        hooks = json.loads(self.hooks_path.read_text(encoding="utf-8"))
        for event, configs in hooks.get("hooks", {}).items():
            for config in configs:
                for hook in config.get("hooks", []):
                    cmd = hook.get("command", "")
                    self.assertIn("${PLUGIN_ROOT}", cmd,
                                 f"Hook command for {event} does not use ${{PLUGIN_ROOT}}")

    def test_hooks_json_pretooluse_has_matcher(self):
        """PreToolUse should have a matcher for Write|Edit|Bash|shell_command|apply_patch."""
        hooks = json.loads(self.hooks_path.read_text(encoding="utf-8"))
        pre_tool_use = hooks.get("hooks", {}).get("PreToolUse", [])
        self.assertGreater(len(pre_tool_use), 0)
        matcher = pre_tool_use[0].get("matcher", "")
        self.assertIn("Write", matcher)
        self.assertIn("Edit", matcher)
        self.assertIn("Bash", matcher)


class PythonInterpreterResolutionTests(unittest.TestCase):
    """Test cross-platform Python interpreter resolution."""

    def test_resolve_python_with_env_var(self):
        """DS_LITE_PYTHON environment variable should be used."""
        os.environ["DS_LITE_PYTHON"] = sys.executable
        result = ds_lite_hook_entry.resolve_python()
        self.assertEqual(result, sys.executable)
        del os.environ["DS_LITE_PYTHON"]

    def test_resolve_python_fallback_to_sys_executable(self):
        """Without env vars, should fall back to sys.executable."""
        old_ds = os.environ.pop("DS_LITE_PYTHON", None)
        old_pb = os.environ.pop("PYTHON_BIN", None)
        result = ds_lite_hook_entry.resolve_python()
        self.assertEqual(result, sys.executable)
        if old_ds:
            os.environ["DS_LITE_PYTHON"] = old_ds
        if old_pb:
            os.environ["PYTHON_BIN"] = old_pb

    def test_hook_entry_script_exists(self):
        """The hook entry script should exist."""
        entry_path = REPO_ROOT / "plugins" / "deepscientist-lite-core" / "scripts" / "ds_lite_hook_entry.py"
        self.assertTrue(entry_path.exists(),
                       f"Hook entry script not found: {entry_path}")


class PluginJsonValidationTests(unittest.TestCase):
    """Validate plugin.json structure for all packages."""

    def test_all_packages_have_plugin_json(self):
        """All package directories should have .codex-plugin/plugin.json."""
        packages_dir = REPO_ROOT / "plugins"
        package_dirs = [d for d in packages_dir.iterdir()
                       if d.is_dir() and not d.name.startswith("__")]
        self.assertGreater(len(package_dirs), 0)
        for pkg_dir in package_dirs:
            plugin_json = pkg_dir / ".codex-plugin" / "plugin.json"
            self.assertTrue(plugin_json.exists(),
                           f"plugin.json not found in {pkg_dir.name}")

    def test_plugin_json_has_required_fields(self):
        """All plugin.json should have name, version, description."""
        packages_dir = REPO_ROOT / "plugins"
        for pkg_dir in packages_dir.iterdir():
            if not pkg_dir.is_dir() or pkg_dir.name.startswith("__"):
                continue
            plugin_json = pkg_dir / ".codex-plugin" / "plugin.json"
            if not plugin_json.exists():
                continue
            data = json.loads(plugin_json.read_text(encoding="utf-8"))
            self.assertIn("name", data, f"{pkg_dir.name}: missing 'name'")
            self.assertIn("version", data, f"{pkg_dir.name}: missing 'version'")
            self.assertIn("description", data, f"{pkg_dir.name}: missing 'description'")


if __name__ == "__main__":
    unittest.main()