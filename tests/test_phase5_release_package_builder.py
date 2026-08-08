from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from tools.validation.phase5_release_package_builder import (
    PACKAGE_DIRECTORIES,
    build_release_packages,
)


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
        marketplace = repository / ".agents" / "plugins" / "marketplace.json"
        marketplace.parent.mkdir(parents=True)
        marketplace.write_text(
            json.dumps({
                "name": "deepscientist-lite",
                "plugins": [{
                    "name": directory,
                    "source": {
                        "source": "local",
                        "path": f"./plugins/{directory}",
                    },
                } for directory in PACKAGE_DIRECTORIES],
            }),
            encoding="utf-8",
        )
        for directory in PACKAGE_DIRECTORIES:
            plugin = repository / "plugins" / directory
            manifest = plugin / ".codex-plugin" / "plugin.json"
            manifest.parent.mkdir(parents=True)
            payload = {"name": directory, "version": "1.0.0", "skills": "./skills/"}
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
            ])

    def test_builder_is_fresh_only_and_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            repository = self._repository(root)
            first = build_release_packages(repository, root / "first")
            second = build_release_packages(repository, root / "second")
            self.assertEqual(first["package_digest"], second["package_digest"])
            with self.assertRaises(FileExistsError):
                build_release_packages(repository, root / "first")


if __name__ == "__main__":
    unittest.main()
