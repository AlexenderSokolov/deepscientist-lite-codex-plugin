#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

EXPECTED_SKILLS = [
    "ds-lite-intake",
    "ds-lite-scout",
    "ds-lite-idea",
    "ds-lite-experiment",
    "ds-lite-review",
    "ds-lite-analysis-write",
]


def fail(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def run(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(cmd, cwd=str(cwd), text=True, encoding="utf-8", capture_output=True)
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
    if manifest.get("version") != "0.3.0-beta.1":
        fail("plugin version must be 0.3.0-beta.1")
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
    evidence_script = plugin_root / "scripts" / "ds_lite_evidence.py"
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
    for relative in (
        "research/artifacts/scout-smoke.md",
        "research/artifacts/idea-smoke.md",
        "research/artifacts/experiment-smoke.md",
        "research/artifacts/review-smoke.md",
        "research/artifacts/analysis-smoke.md",
        "outputs/metrics.json",
        "outputs/result.json",
        "stdout.log",
        "stderr.log",
    ):
        path = smoke_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}\n" if path.suffix == ".json" else "# Smoke artifact\n", encoding="utf-8")
    (smoke_root / "outputs" / "metrics.json").write_text('{"score": 0.9}\n', encoding="utf-8")
    (smoke_root / "outputs" / "result.json").write_text('{"ok": true}\n', encoding="utf-8")
    contract_path = smoke_root / "contract.json"
    contract_path.write_text(
        json.dumps(
            {
                "schema_version": "ds-lite.experiment-contract.v1",
                "run_id": "smoke-run",
                "node_id": "experiment-node",
                "hypothesis": "The smoke route should meet its deterministic score threshold.",
                "command": "python smoke.py",
                "cwd": ".",
                "inputs": [],
                "metrics": [{"name": "score", "direction": "max", "threshold": 0.8}],
                "seeds": [0],
                "budget": {"value": 1, "unit": "run"},
                "expected_outputs": ["outputs/result.json"],
                "failure_interpretation": "A missing output or score below 0.8 blocks analysis.",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    environment_path = smoke_root / "environment.json"
    environment_path.write_text(
        json.dumps(
            {
                "schema_version": "ds-lite.environment.v1",
                "python": sys.version.split()[0],
                "platform": sys.platform,
                "packages": [],
                "container": "not-applicable",
                "hardware": "validation runner",
                "notes": "sanitized smoke environment",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    unicode_root = Path(tempfile.mkdtemp(prefix="ds-lite-unicode-"))
    title_file = unicode_root / "title.txt"
    question_file = unicode_root / "question.txt"
    title_file.write_text("中文标题", encoding="utf-8")
    question_file.write_text("能否正确保存中文问题？", encoding="utf-8")
    run(
        [
            sys.executable,
            str(state_script),
            "init",
            "--root",
            str(unicode_root),
            "--title-file",
            str(title_file),
            "--question-file",
            str(question_file),
        ],
        repo_root,
    )
    run(
        [sys.executable, str(evidence_script), "init", "--root", str(smoke_root), "--run-id", "smoke-run", "--contract", str(contract_path)],
        repo_root,
    )
    run(
        [
            sys.executable,
            str(evidence_script),
            "finalize",
            "--root",
            str(smoke_root),
            "--run-id",
            "smoke-run",
            "--exit-code",
            "0",
            "--stdout",
            str(smoke_root / "stdout.log"),
            "--stderr",
            str(smoke_root / "stderr.log"),
            "--metrics",
            str(smoke_root / "outputs" / "metrics.json"),
            "--environment",
            str(environment_path),
            "--output",
            "outputs/result.json",
        ],
        repo_root,
    )
    run([sys.executable, str(evidence_script), "verify", "--root", str(smoke_root), "--run-id", "smoke-run", "--strict"], repo_root)
    unicode_graph = json.loads((unicode_root / "research" / "state" / "graph.json").read_text(encoding="utf-8"))
    unicode_summary = unicode_graph["nodes"]["intake-root"]["summary"]
    if unicode_summary != "能否正确保存中文问题？":
        fail("unicode question-file smoke failed")
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
            "--evidence-path",
            "research/evidence/smoke-run/manifest.json",
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
            "add-node",
            "--root",
            str(smoke_root),
            "--id",
            "review-node",
            "--kind",
            "review",
            "--parent",
            "experiment-node",
            "--relation",
            "next",
            "--title",
            "Review smoke evidence",
            "--artifact-path",
            "research/artifacts/review-smoke.md",
            "--evidence-path",
            "research/evidence/smoke-run/manifest.json",
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
            "analysis-node",
            "--kind",
            "analysis",
            "--parent",
            "review-node",
            "--relation",
            "next",
            "--title",
            "Analyze reviewed smoke evidence",
            "--artifact-path",
            "research/artifacts/analysis-smoke.md",
            "--active",
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
    run([sys.executable, str(state_script), "trace", "--root", str(smoke_root), "--node", "analysis-node"], repo_root)
    run(
        [
            sys.executable,
            str(state_script),
            "trace",
            "--root",
            str(smoke_root),
            "--node",
            "analysis-node",
            "--format",
            "markdown",
        ],
        repo_root,
    )
    run([sys.executable, str(state_script), "status", "--root", str(smoke_root), "--json"], repo_root)
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
    run([sys.executable, str(state_script), "validate", "--root", str(smoke_root), "--strict"], repo_root)
    run([sys.executable, str(state_script), "render-map", "--root", str(smoke_root)], repo_root)
    if not (smoke_root / "RESEARCH_MAP.md").exists():
        fail("smoke project did not render RESEARCH_MAP.md")


def validate_docs(repo_root: Path, plugin_root: Path) -> None:
    required_paths = [
        repo_root / "README.md",
        repo_root / "README.zh.md",
        repo_root / "docs" / "README.md",
        repo_root / "docs" / "user-guide.zh.md",
        repo_root / "docs" / "implementation.zh.md",
        repo_root / "teaching" / "README.zh.md",
        repo_root / "teaching" / "demo-script.zh.md",
        repo_root / "teaching" / "lesson-plan.zh.md",
        repo_root / "teaching" / "instructor-guide.zh.md",
        repo_root / "teaching" / "cases" / "paradigm-comparison-case.md",
        repo_root / "teaching" / "quickstart-20.zh.md",
        repo_root / "teaching" / "evidence-lab-45.zh.md",
        repo_root / "teaching" / "scored-branch-lab-90.zh.md",
        repo_root / "teaching" / "route-lab-30.zh.md",
        repo_root / "teaching" / "path-lab-30.zh.md",
        repo_root / "teaching" / "revision-lab-30.zh.md",
        repo_root / "teaching" / "student-worksheet.zh.md",
        repo_root / "teaching" / "instructor-rubric.zh.md",
        repo_root / "teaching" / "answer-key.zh.md",
        repo_root / "teaching" / "run_evidence_lab.sh",
        repo_root / "teaching" / "lab_runner.py",
        repo_root / "teaching" / "run_lab.sh",
        repo_root / "teaching" / "run_lab.ps1",
        repo_root / "docs" / "maintainers" / "v0.3-recommendation-assessment.zh.md",
        repo_root / "docs" / "maintainers" / "v0.3-audit.zh.md",
        repo_root / "docs" / "maintainers" / "writing-guide.zh.md",
        repo_root / "PACKAGE.md",
        repo_root / ".gitattributes",
        repo_root / "PROJECT.md",
        plugin_root / "scripts" / "ds_lite_evidence.py",
        plugin_root / "assets" / "templates" / "research" / "evidence" / "contract.json",
        plugin_root / "assets" / "templates" / "research" / "evidence" / "environment.json",
        plugin_root / "assets" / "templates" / "run_review.sh",
        repo_root / "LICENSE",
        repo_root / "NOTICE",
        repo_root / "CHANGELOG.md",
        repo_root / "docs" / "maintainers" / "graph-v2-migration.md",
        repo_root / "docs" / "maintainers" / "v0.2-audit.zh.md",
    ]
    for item in required_paths:
        if not item.exists():
            fail(f"missing documentation file: {item}")

    readme = (repo_root / "README.md").read_text(encoding="utf-8")
    for required_link in ("README.zh.md", "docs/user-guide.zh.md", "docs/README.md", "teaching/README.zh.md", "plugins/deepscientist-lite/"):
        if required_link not in readme:
            fail(f"README.md missing link to {required_link}")
    for forbidden in ("Current E2E Status", "0.1.2 update", "0.1.3 beta update", "sanitization", "product-positioning"):
        if forbidden in readme:
            fail(f"README.md contains maintainer/status content: {forbidden}")

    runtime_refs = {path.name for path in (plugin_root / "references").glob("*.md")}
    expected_refs = {
        "state-graph-protocol.md",
        "evidence-pack-protocol.md",
        "experiment-comparison-template.md",
        "math-exploration-template.md",
        "teaching-guide.zh.md",
    }
    if runtime_refs != expected_refs:
        fail(f"runtime references mismatch: {sorted(runtime_refs)}")

    if (repo_root / "docs" / "sanitization-report.md").exists():
        fail("docs/sanitization-report.md should not be user-facing documentation")
    for root_only in ("run_validate.sh", "run_validate.ps1"):
        if (repo_root / root_only).exists():
            fail(f"root validation wrapper should not exist: {root_only}")
    if (repo_root / "scripts").exists():
        fail("root scripts directory should not exist")

    public_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in [
            repo_root / "README.zh.md",
            repo_root / "docs" / "user-guide.zh.md",
            repo_root / "teaching" / "README.zh.md",
            repo_root / "teaching" / "quickstart-20.zh.md",
            repo_root / "teaching" / "evidence-lab-45.zh.md",
            repo_root / "teaching" / "scored-branch-lab-90.zh.md",
        ]
    )
    for overclaim in ("完美逆向", "绝对可追溯", "完整推理链条", "彻底杜绝虚假", "零幻觉"):
        if overclaim in public_text:
            fail(f"public documentation contains an overstated claim: {overclaim}")

    markdown_files = [repo_root / "README.md", repo_root / "README.zh.md"]
    markdown_files.extend((repo_root / "docs").rglob("*.md"))
    markdown_files.extend((repo_root / "teaching").rglob("*.md"))
    markdown_files.extend((plugin_root / "references").rglob("*.md"))
    for markdown in markdown_files:
        text = markdown.read_text(encoding="utf-8-sig")
        for target in re.findall(r"\[[^\]]+\]\(([^)]+)\)", text):
            if target.startswith(("http://", "https://", "#", "codex://", "mailto:")):
                continue
            relative = target.split("#", 1)[0]
            if relative and not (markdown.parent / relative).resolve().exists():
                fail(f"broken local Markdown link in {markdown}: {target}")


def validate_teaching_runner(repo_root: Path) -> None:
    lab_runner = repo_root / "teaching" / "lab_runner.py"
    parent = Path(tempfile.mkdtemp(prefix="ds-lite-teaching-smoke-"))
    output = parent / "workspace with spaces"
    run(
        [
            sys.executable,
            str(lab_runner),
            "--lab",
            "quickstart",
            "--mode",
            "student",
            "--output",
            str(output),
        ],
        repo_root,
    )
    if (output / "REFERENCE_ANSWER.md").exists():
        fail("student teaching mode must not create a reference answer")
    graph = json.loads((output / "project" / "research" / "state" / "graph.json").read_text(encoding="utf-8"))
    if graph.get("active_node_id") != "idea-file-handoff":
        fail("quickstart teaching smoke did not reach the expected idea node")
    if sys.platform != "win32":
        compatibility_output = parent / "compatibility evidence workspace"
        run(
            ["bash", str(repo_root / "teaching" / "run_evidence_lab.sh"), str(compatibility_output)],
            repo_root,
        )
        if not (compatibility_output / "project" / "research" / "evidence" / "evidence-demo" / "manifest.json").exists():
            fail("run_evidence_lab.sh compatibility entry did not produce an Evidence Pack")


def main() -> int:
    repo_root = Path(__file__).resolve().parents[2]
    plugin_root = repo_root / "plugins" / "deepscientist-lite"
    validate_manifest(plugin_root)
    validate_skills(plugin_root)
    validate_docs(repo_root, plugin_root)
    validate_teaching_runner(repo_root)
    validate_state_script(repo_root, plugin_root)
    print("OK: DeepScientist Lite plugin repository validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
