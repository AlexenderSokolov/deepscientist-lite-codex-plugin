from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from tools.validation.phase5_release_package_builder import (
    PACKAGE_DIRECTORIES,
    build_release_packages,
)
from tools.validation.release_identity import load_package_set


def tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        relative = path.relative_to(root).as_posix().encode("utf-8")
        content = path.read_bytes()
        digest.update(relative + b"\0" + hashlib.sha256(content).digest())
    return digest.hexdigest()


class Phase5ReleasePackageBuilderTests(unittest.TestCase):
    def _repository(self, root: Path) -> Path:
        repository = root / "repository"
        package_set = load_package_set(Path(__file__).resolve().parents[1])
        release = repository / "release"
        release.mkdir(parents=True)
        (release / "package-set.json").write_text(json.dumps(package_set), encoding="utf-8")
        marketplace = repository / ".agents" / "plugins" / "marketplace.json"
        marketplace.parent.mkdir(parents=True)
        marketplace.write_text(
            json.dumps({
                "name": "deepscientist-lite",
                "plugins": [{
                "name": package["name"],
                    "source": {
                        "source": "local",
                        "path": f"./plugins/{package['directory']}",
                    },
                } for package in package_set["packages"].values()],
            }),
            encoding="utf-8",
        )
        packages_by_directory = {
            package["directory"]: package
            for package in package_set["packages"].values()
        }
        for directory in PACKAGE_DIRECTORIES:
            plugin = repository / "plugins" / directory
            manifest = plugin / ".codex-plugin" / "plugin.json"
            manifest.parent.mkdir(parents=True)
            expected = packages_by_directory[directory]
            payload = {"name": expected["name"], "version": expected["version"], "skills": "./skills/"}
            if directory == "deepscientist-lite-core":
                payload["hooks"] = "./hooks/hooks.json"
                hooks = plugin / "hooks" / "hooks.json"
                hooks.parent.mkdir(parents=True)
                hooks.write_text(
                    json.dumps({"hooks": {
                        "UserPromptSubmit": [], "PreToolUse": [],
                        "PostToolUse": [], "Stop": [],
                    }}),
                    encoding="utf-8",
                )
            manifest.write_text(json.dumps(payload), encoding="utf-8")
            if directory != "deepscientist-lite-core":
                (plugin / "compatibility.json").write_text(
                    json.dumps({
                        "schema_version": "ds-lite.pack-compatibility.v1",
                        "pack": {"plugin": expected["name"], "version": expected["version"]},
                        "requires": {"plugin": "deepscientist-lite", "version": package_set["core_compatibility"]},
                        "missing_core": "blocked",
                    }),
                    encoding="utf-8",
                )
            skill = plugin / "skills" / "sample" / "SKILL.md"
            skill.parent.mkdir(parents=True)
            skill.write_text("---\nname: sample\ndescription: sample\n---\n", encoding="utf-8")
            cache = plugin / "__pycache__" / "ignored.pyc"
            cache.parent.mkdir()
            cache.write_bytes(b"cache")
        return repository

    def test_builder_projects_only_redundant_core_hook_manifest_field(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            repository = self._repository(root)
            source_manifest = repository / "plugins" / "deepscientist-lite-core" / ".codex-plugin" / "plugin.json"
            source_before = source_manifest.read_bytes()
            output = root / "package"
            result = build_release_packages(repository, output)

            packaged_manifest = json.loads(
                (output / "plugins" / "deepscientist-lite-core" / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
            )
            self.assertNotIn("hooks", packaged_manifest)
            self.assertEqual(source_manifest.read_bytes(), source_before)
            self.assertTrue((output / "plugins" / "deepscientist-lite-core" / "hooks" / "hooks.json").is_file())
            self.assertFalse((output / "plugins" / "deepscientist-lite-core" / "controller").exists())
            packaged_marketplace = json.loads(
                (output / ".agents" / "plugins" / "marketplace.json").read_text(encoding="utf-8")
            )
            self.assertEqual(
                [item["source"]["path"] for item in packaged_marketplace["plugins"]],
                [f"./plugins/{directory}" for directory in PACKAGE_DIRECTORIES],
            )
            self.assertFalse(any(path.name == "__pycache__" for path in output.rglob("*")))
            self.assertEqual(result["status"], "passed")
            self.assertEqual(result["package_digest"], tree_digest(output))
            self.assertEqual(result["transforms"], [
                {
                    "package": "deepscientist-lite-core",
                    "operation": "remove-redundant-hooks-manifest-field",
                },
                {
                    "package": "deepscientist-lite-core",
                    "operation": "exclude-compatibility-control-plane-runtime",
                },
                {
                    "package": "deepscientist-lite-academic",
                    "operation": "archive-high-resolution-examples",
                },
            ])
            sbom = json.loads((output / "package-sbom.json").read_text(encoding="utf-8"))
            self.assertEqual(sbom["schema_version"], "ds-lite.package-sbom.v1")
            self.assertEqual(len(sbom["packages"]), 7)

    def test_builder_is_fresh_only_and_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            repository = self._repository(root)
            first = build_release_packages(repository, root / "first")
            second = build_release_packages(repository, root / "second")
            self.assertEqual(first["package_digest"], second["package_digest"])
            with self.assertRaises(FileExistsError):
                build_release_packages(repository, root / "first")

    def test_builder_moves_high_resolution_academic_examples_to_an_optional_archive(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            repository = self._repository(root)
            example = repository / "plugins" / "deepscientist-lite-academic" / "skills" / "nature-figure" / "assets" / "figures4papers" / "preview.png"
            example.parent.mkdir(parents=True)
            example.write_bytes(b"high-resolution-preview")
            output = root / "package"
            result = build_release_packages(repository, output)
            self.assertFalse((output / "plugins" / "deepscientist-lite-academic" / "skills" / "nature-figure" / "assets" / "figures4papers").exists())
            archive = output / "academic-examples.zip"
            self.assertTrue(archive.is_file())
            self.assertTrue(result["academic_examples"]["included"])
            with zipfile.ZipFile(archive) as bundle:
                self.assertIn(
                    "plugins/deepscientist-lite-academic/skills/nature-figure/assets/figures4papers/preview.png",
                    bundle.namelist(),
                )


if __name__ == "__main__":
    unittest.main()
