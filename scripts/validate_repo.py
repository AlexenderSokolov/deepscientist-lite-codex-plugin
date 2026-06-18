#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

EXPECTED_SKILLS = [
    "ds-lite-intake",
    "ds-lite-scout",
    "ds-lite-idea",
    "ds-lite-experiment",
    "ds-lite-analysis-write",
]


def fail(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def run(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(cmd, cwd=str(cwd), text=True, capture_output=True)
    if result.returncode != 0:
        print(result.stdout)
        print(result.stderr, file=sys.stderr)
        fail("command failed: " + " ".join(cmd))
    return result


def parse_frontmatter(path: Path) -> dict[str, str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != "---":
        fail(f"{path} missing YAML frontmatter")
    end = None
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            end = index
            break
    if end is None:
        fail(f"{path} frontmatter is not closed")
    data: dict[str, str] = {}
    for line in lines[1:end]:
        if not line.strip():
            continue
        if ":" not in line:
            fail(f"{path} has invalid frontmatter line: {line}")
        key, value = line.split(":", 1)
        data[key.strip()] = value.strip()
    return data


def validate_manifest(plugin_root: Path) -> None:
    manifest_path = plugin_root / ".codex-plugin" / "plugin.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("name") != "deepscientist-lite":
        fail("plugin name must be deepscientist-lite")
    if manifest.get("version") != "0.1.0":
        fail("plugin version must be 0.1.0")
    if manifest.get("skills") != "./skills/":
        fail("plugin skills path must be ./skills/")
    for forbidden in ("mcpServers", "apps", "hooks"):
        if forbidden in manifest:
            fail(f"plugin manifest must not declare {forbidden}")
    if "TODO" in manifest_path.read_text(encoding="utf-8"):
        fail("plugin manifest still contains TODO")


def validate_skills(plugin_root: Path) -> None:
    skills_root = plugin_root / "skills"
    for skill_name in EXPECTED_SKILLS:
        skill_file = skills_root / skill_name / "SKILL.md"
        if not skill_file.exists():
            fail(f"missing skill: {skill_name}")
        text = skill_file.read_text(encoding="utf-8")
        if "TODO" in text or "[TODO" in text:
            fail(f"{skill_file} still contains TODO")
        data = parse_frontmatter(skill_file)
        if set(data) != {"name", "description"}:
            fail(f"{skill_file} frontmatter must contain only name and description")
        if data["name"] != skill_name:
            fail(f"{skill_file} name mismatch")
        if len(data["description"]) < 80:
            fail(f"{skill_file} description is too short to trigger reliably")


def validate_state_script(repo_root: Path, plugin_root: Path) -> None:
    state_script = plugin_root / "scripts" / "ds_lite_state.py"
    smoke_root = Path(tempfile.mkdtemp(prefix="ds-lite-smoke-"))
    print(f"Smoke project: {smoke_root}")

    run(
        [
            sys.executable,
            str(state_script),
            "init",
            "--root",
            str(smoke_root),
            "--title",
            "Smoke Project",
            "--project-id",
            "smoke-project",
            "--question",
            "Can DS Lite trace a lightweight research route?",
        ],
        repo_root,
    )
    run(
        [
            sys.executable,
            str(state_script),
            "add-node",
            "--root",
            str(smoke_root),
            "--id",
            "scout-node",
            "--kind",
            "scout",
            "--parent",
            "intake-root",
            "--relation",
            "next",
            "--title",
            "Scout baseline",
            "--summary",
            "Baseline and metric scoped.",
            "--artifact-path",
            "research/artifacts/scout-smoke.md",
        ],
        repo_root,
    )
    run(
        [
            sys.executable,
            str(state_script),
            "add-node",
            "--root",
            str(smoke_root),
            "--id",
            "idea-node",
            "--kind",
            "idea",
            "--parent",
            "scout-node",
            "--relation",
            "branch",
            "--title",
            "Cheap validation idea",
            "--summary",
            "Use the cheapest experiment that can falsify the route.",
            "--artifact-path",
            "research/artifacts/idea-smoke.md",
            "--active",
        ],
        repo_root,
    )
    run(
        [
            sys.executable,
            str(state_script),
            "add-node",
            "--root",
            str(smoke_root),
            "--id",
            "experiment-node",
            "--kind",
            "experiment",
            "--parent",
            "idea-node",
            "--relation",
            "next",
            "--title",
            "Smoke experiment",
            "--summary",
            "Record one reproducible experiment.",
            "--artifact-path",
            "research/artifacts/experiment-smoke.md",
            "--active",
            "--render",
        ],
        repo_root,
    )
    run(
        [
            sys.executable,
            str(state_script),
            "add-edge",
            "--root",
            str(smoke_root),
            "--from",
            "experiment-node",
            "--to",
            "idea-node",
            "--relation",
            "supports",
            "--reason",
            "Smoke experiment supports the selected idea",
        ],
        repo_root,
    )
    run(
        [
            sys.executable,
            str(state_script),
            "link-artifact",
            "--root",
            str(smoke_root),
            "--node",
            "experiment-node",
            "--path",
            "outputs/metrics.json",
        ],
        repo_root,
    )
    run([sys.executable, str(state_script), "trace", "--root", str(smoke_root), "--node", "experiment-node"], repo_root)
    run(
        [
            sys.executable,
            str(state_script),
            "trace-artifact",
            "--root",
            str(smoke_root),
            "--path",
            "research/artifacts/experiment-smoke.md",
        ],
        repo_root,
    )
    run([sys.executable, str(state_script), "validate", "--root", str(smoke_root)], repo_root)
    run([sys.executable, str(state_script), "render-map", "--root", str(smoke_root)], repo_root)
    if not (smoke_root / "RESEARCH_MAP.md").exists():
        fail("smoke project did not render RESEARCH_MAP.md")


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    plugin_root = repo_root / "plugins" / "deepscientist-lite"
    validate_manifest(plugin_root)
    validate_skills(plugin_root)
    validate_state_script(repo_root, plugin_root)
    print("OK: DeepScientist Lite plugin repository validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

