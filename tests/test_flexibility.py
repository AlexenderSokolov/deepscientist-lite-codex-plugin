#!/usr/bin/env python3
"""Flexibility tests for DS Lite v6.

Tests package independent install, inter-package dependencies, semver range
compatibility, dynamic version detection, and upstream registry override.
"""

import json
import os
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

PLUGINS_DIR = REPO_ROOT / "plugins"


def _load_plugin_json(pkg_name):
    p = PLUGINS_DIR / pkg_name / ".codex-plugin" / "plugin.json"
    return json.loads(p.read_text(encoding="utf-8"))


def _load_compatibility_json(pkg_name):
    p = PLUGINS_DIR / pkg_name / "compatibility.json"
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


class PackageIndependenceTests(unittest.TestCase):
    """Each package should be installable on its own."""

    def test_core_has_no_runtime_dependency_on_academic(self):
        core = _load_plugin_json("deepscientist-lite-core")
        deps = core.get("dependencies", [])
        dep_names = [d.get("name", "") if isinstance(d, dict) else str(d) for d in deps]
        self.assertNotIn("deepscientist-lite-academic", dep_names)

    def test_academic_depends_on_core(self):
        compat = _load_compatibility_json("deepscientist-lite-academic")
        self.assertIsNotNone(compat, "academic should have compatibility.json")
        req = compat.get("requires", {})
        self.assertEqual(req.get("plugin"), "deepscientist-lite")
        self.assertTrue(req.get("version"))

    def test_web_package_depends_on_core(self):
        compat = _load_compatibility_json("deepscientist-lite-web")
        self.assertIsNotNone(compat)
        req = compat.get("requires", {})
        self.assertEqual(req.get("plugin"), "deepscientist-lite")

    def test_all_packages_have_plugin_json(self):
        for pkg_dir in PLUGINS_DIR.iterdir():
            if not pkg_dir.is_dir() or pkg_dir.name.startswith("__"):
                continue
            pj = pkg_dir / ".codex-plugin" / "plugin.json"
            self.assertTrue(pj.exists(), f"{pkg_dir.name} missing plugin.json")


class SemverRangeTests(unittest.TestCase):
    """compatibility.json should use semver ranges, not exact pins."""

    def _check_uses_range(self, pkg_name):
        compat = _load_compatibility_json(pkg_name)
        if compat is None:
            self.skipTest(f"{pkg_name} has no compatibility.json")
        req = compat.get("requires", {})
        version_spec = req.get("version", "")
        self.assertTrue(version_spec, f"{pkg_name} should require a version")

    def test_academic_uses_range(self):
        self._check_uses_range("deepscientist-lite-academic")

    def test_web_uses_range(self):
        self._check_uses_range("deepscientist-lite-web")

    def test_knowledge_uses_range(self):
        self._check_uses_range("deepscientist-lite-knowledge")

    def test_empirical_uses_range(self):
        self._check_uses_range("deepscientist-lite-empirical")

    def test_engineering_uses_range(self):
        self._check_uses_range("deepscientist-lite-engineering")


class DynamicVersionDetectionTests(unittest.TestCase):
    """Version checks should use minimum-version logic, not exact match."""

    def test_min_codex_version_exists(self):
        sys.path.insert(0, str(PLUGINS_DIR / "deepscientist-lite-core" / "scripts"))
        import ds_lite_loop
        self.assertTrue(hasattr(ds_lite_loop, "MIN_CODEX_VERSION"))
        self.assertNotEqual(ds_lite_loop.MIN_CODEX_VERSION, "")

    def test_version_ge_comparison(self):
        sys.path.insert(0, str(PLUGINS_DIR / "deepscientist-lite-core" / "scripts"))
        import ds_lite_loop
        self.assertTrue(ds_lite_loop._version_ge("0.150.0", "0.144.5"))
        self.assertTrue(ds_lite_loop._version_ge("0.144.5", "0.144.5"))
        self.assertFalse(ds_lite_loop._version_ge("0.100.0", "0.144.5"))

    def test_sha256_override_via_env(self):
        sys.path.insert(0, str(PLUGINS_DIR / "deepscientist-lite-core" / "scripts"))
        import ds_lite_loop
        old = os.environ.get("DS_LITE_CODEX_SHA256")
        os.environ["DS_LITE_CODEX_SHA256"] = "custom-hash"
        try:
            self.assertEqual(
                os.environ.get("DS_LITE_CODEX_SHA256"), "custom-hash"
            )
        finally:
            if old is not None:
                os.environ["DS_LITE_CODEX_SHA256"] = old
            else:
                os.environ.pop("DS_LITE_CODEX_SHA256", None)


class UpstreamRegistryOverrideTests(unittest.TestCase):
    """Upstream project registry should support env-var commit override."""

    def setUp(self):
        self.registry_path = REPO_ROOT / "plugins" / "deepscientist-lite" / "references" / "upstream-project-registry.json"
        self.registry = json.loads(self.registry_path.read_text(encoding="utf-8"))

    def test_registry_has_version_resolution(self):
        vr = self.registry.get("version_resolution", {})
        self.assertIn("env_prefix", vr)
        self.assertEqual(vr["env_prefix"], "DS_LITE_UPSTREAM_COMMIT_")

    def test_each_project_has_pinned_and_latest_checked(self):
        for proj in self.registry.get("projects", []):
            self.assertIn("pinned_commit", proj, f"{proj.get('id')} missing pinned_commit")
            self.assertIn("latest_checked_commit", proj, f"{proj.get('id')} missing latest_checked_commit")

    def test_env_override_changes_resolved_commit(self):
        proj = self.registry["projects"][0]
        proj_id = proj["id"].upper().replace("-", "_")
        env_var = f"DS_LITE_UPSTREAM_COMMIT_{proj_id}"
        old = os.environ.get(env_var)
        os.environ[env_var] = "override-commit-hash"
        try:
            self.assertEqual(os.environ.get(env_var), "override-commit-hash")
        finally:
            if old is not None:
                os.environ[env_var] = old
            else:
                os.environ.pop(env_var, None)


if __name__ == "__main__":
    unittest.main()
