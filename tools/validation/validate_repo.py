#!/usr/bin/env python3
from __future__ import annotations

import hashlib
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
    "ds-lite-iterate",
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
    if manifest.get("version") != "0.4.0-beta.2":
        fail("plugin version must be 0.4.0-beta.2")
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
    initial_mission = json.loads(
        run(
            [sys.executable, str(state_script), "mission", "--root", str(smoke_root), "--format", "json"],
            repo_root,
        ).stdout
    )
    if initial_mission.get("evidence_strength") != "planning":
        fail("new-project mission must begin with planning evidence strength")
    if initial_mission.get("claim_readiness") != "none":
        fail("new-project mission must begin with claim readiness none")
    work_unit_path = smoke_root / "research" / "work-unit.json"
    if not work_unit_path.is_file():
        fail("init did not create research/work-unit.json")
    for relative in (
        "research/artifacts/scout-smoke.md",
        "research/artifacts/idea-smoke.md",
        "research/artifacts/experiment-smoke.md",
        "research/artifacts/experiment-failed-branch.md",
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
    manifest_ref = "research/evidence/smoke-run/manifest.json"
    manifest_path = smoke_root / manifest_ref
    manifest_sha = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    digest_records = [{"path": manifest_ref, "sha256": manifest_sha}]
    evidence_digest = hashlib.sha256(
        json.dumps(digest_records, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    work_unit_path.write_text(
        json.dumps(
            {
                "schema_version": "ds-lite.work-unit.v1",
                "work_unit_id": "work-smoke",
                "title": "Validate typed evidence and review",
                "goal": "Exercise the P0 evidence and review semantics.",
                "execution_mode": "inline",
                "profile_id": "experiment-run",
                "state": "active",
                "prerequisites": [],
                "required_capabilities": ["read"],
                "evidence_requirements": [
                    {"kind": "experiment-pack", "validator": "ds-lite.evidence.v1"}
                ],
                "evidence_refs": [manifest_ref],
                "resource_limits": [{"dimension": "actions", "unit": "count", "value": 1}],
                "subjects": [
                    {
                        "kind": "artifact",
                        "id": "smoke-graph",
                        "query_ref": "research/state/graph.json",
                    }
                ],
                "active_iteration_ref": "",
                "extensions": {},
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    review_result_ref = "research/artifacts/review-smoke.json"
    (smoke_root / review_result_ref).write_text(
        json.dumps(
            {
                "schema_version": "ds-lite.review-result.v1",
                "review_id": "review-node",
                "work_unit_id": "work-smoke",
                "profile_id": "experiment-run",
                "review_node_id": "review-node",
                "reviewed_node_id": "experiment-node",
                "reviewed_evidence_refs": [manifest_ref],
                "evidence_validator": "ds-lite.evidence.v1",
                "evidence_digest": evidence_digest,
                "verdict": "pass",
                "claim_assessment": "supportable",
                "channels": {"integrity": "pass"},
                "limitations": [],
                "review_artifact_ref": "research/artifacts/review-smoke.md",
                "completed_at": "2026-07-16T00:00:00Z",
                "extensions": {},
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
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
            "experiment-failed-branch",
            "--kind",
            "experiment",
            "--status",
            "blocked",
            "--parent",
            "idea-node",
            "--relation",
            "branch",
            "--title",
            "Failed off-route experiment",
            "--summary",
            "A failed branch is preserved as branch debt instead of being erased.",
            "--artifact-path",
            "research/artifacts/experiment-failed-branch.md",
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
            "experiment-failed-branch",
            "--to",
            "idea-node",
            "--relation",
            "rollback",
            "--reason",
            "Return to the validated idea after the failed branch.",
            "--artifact-path",
            "research/artifacts/experiment-failed-branch.md",
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
            "--artifact-path",
            review_result_ref,
            "--evidence-path",
            manifest_ref,
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
    run(
        [
            sys.executable,
            str(state_script),
            "validate",
            "--root",
            str(smoke_root),
            "--strict",
            "--scope",
            "active-route",
        ],
        repo_root,
    )
    mission_result = run(
        [sys.executable, str(state_script), "mission", "--root", str(smoke_root), "--format", "json"],
        repo_root,
    )
    mission = json.loads(mission_result.stdout)
    if mission.get("active_node_id") != "analysis-node":
        fail("mission smoke did not preserve the analysis active node")
    if "analysis-node" not in mission.get("active_route", []):
        fail("mission smoke did not show the active analysis route")
    if "artifact != progress" not in mission.get("readiness_rules", []):
        fail("mission smoke did not expose AIResearch readiness rules")
    if not any(item.get("to") == "idea-node" for item in mission.get("rollback_targets", [])):
        fail("mission smoke did not expose the rollback target")
    if not any(item.get("id") == "experiment-failed-branch" for item in mission.get("blocked_nodes", [])):
        fail("mission smoke did not keep the failed branch visible")
    if not any(item.get("name") == "score" and item.get("direction") == "max" for item in mission.get("metric_surfaces", [])):
        fail("mission smoke did not display metric direction from the Evidence Pack contract")
    if not mission.get("validation", {}).get("off_route_warnings"):
        fail("mission smoke did not preserve off-route warnings")
    if mission.get("evidence_strength") != "reviewed":
        fail("mission smoke did not require and accept the typed review result")
    if mission.get("claim_readiness") != "supportable":
        fail("mission smoke did not keep review verdict and claim assessment distinct")
    if mission.get("evidence_detail", {}).get("validated_evidence_count") != 1:
        fail("mission smoke did not report the validated evidence ref")
    if mission.get("evidence_detail", {}).get("review_result_count") != 1:
        fail("mission smoke did not report the typed review result")
    markdown_result = run(
        [sys.executable, str(state_script), "mission", "--root", str(smoke_root), "--format", "markdown"],
        repo_root,
    )
    if not all(
        term in markdown_result.stdout
        for term in ("## Mission Board", "## Metric Surface", "Work unit: `work-smoke`", "Claim readiness: supportable")
    ):
        fail("mission markdown smoke did not render the Mission Board")
    run([sys.executable, str(state_script), "render-status", "--root", str(smoke_root)], repo_root)
    status_text = (smoke_root / "STATUS.md").read_text(encoding="utf-8")
    if "## Mission Board" not in status_text or "analysis-node" not in status_text:
        fail("render-status smoke did not write a user-readable STATUS.md")
    run([sys.executable, str(state_script), "render-map", "--root", str(smoke_root)], repo_root)
    if not (smoke_root / "RESEARCH_MAP.md").exists():
        fail("smoke project did not render RESEARCH_MAP.md")


def validate_docs(repo_root: Path, plugin_root: Path) -> None:
    required_paths = [
        repo_root / "README.md",
        repo_root / "README.zh.md",
        repo_root / "docs" / "README.md",
        repo_root / "docs" / "user-guide.zh.md",
        repo_root / "docs" / "openscience-worker-handoff.zh.md",
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
        repo_root / "docs" / "maintainers" / "v0.3-hardening-log.zh.md",
        repo_root / "docs" / "maintainers" / "writing-guide.zh.md",
        repo_root / "PACKAGE.md",
        repo_root / ".gitattributes",
        repo_root / "PROJECT.md",
        plugin_root / "scripts" / "ds_lite_evidence.py",
        plugin_root / "scripts" / "ds_lite_protocol.py",
        plugin_root / "assets" / "templates" / "research" / "work-unit.json",
        plugin_root / "assets" / "templates" / "research" / "artifacts" / "review-result.json",
        plugin_root / "assets" / "templates" / "research" / "evidence" / "contract.json",
        plugin_root / "assets" / "templates" / "research" / "evidence" / "environment.json",
        plugin_root / "assets" / "templates" / "run_review.sh",
        plugin_root / "assets" / "templates" / "tools" / "ds_lite_runtime.sh",
        repo_root / "LICENSE",
        repo_root / "NOTICE",
        repo_root / "CHANGELOG.md",
        repo_root / "docs" / "maintainers" / "graph-v2-migration.md",
        repo_root / "docs" / "maintainers" / "v0.2-audit.zh.md",
        repo_root / "tools" / "validation" / "prepare_codex_acceptance.py",
        repo_root / "tools" / "validation" / "audit_codex_acceptance.py",
        repo_root / "tools" / "validation" / "run_codex_acceptance.sh",
        repo_root / "tools" / "validation" / "run_codex_acceptance.ps1",
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
        "external-long-task-protocol.md",
        "experiment-comparison-template.md",
        "math-exploration-template.md",
        "teaching-guide.zh.md",
    }
    if runtime_refs != expected_refs:
        fail(f"runtime references mismatch: {sorted(runtime_refs)}")

    p0_doc_requirements = {
        repo_root / "PROJECT.md": ("ds-lite.work-unit.v1", "ds-lite.review-result.v1", "reserved / not-validated"),
        repo_root / "CHANGELOG.md": ("typed review result", "claim readiness"),
        repo_root / "docs" / "user-guide.zh.md": ("ds-lite.work-unit.v1", "claim_assessment", "off-route"),
        repo_root / "docs" / "implementation.zh.md": (
            "ds-lite.review-result.v1",
            "claim_readiness",
            "extensions",
        ),
        repo_root / "docs" / "maintainers" / "known-issues.md": (
            "Markdown-only review",
            "reserved / not-validated",
        ),
        repo_root / "docs" / "maintainers" / "release-status.zh.md": (
            "P0 source validation",
            "cache remains unverified",
        ),
        plugin_root / "references" / "state-graph-protocol.md": (
            "ds-lite.work-unit.v1",
            "ds-lite.review-result.v1",
            "claim_assessment",
            "extensions",
        ),
    }
    for path, required_texts in p0_doc_requirements.items():
        text = path.read_text(encoding="utf-8")
        for required_text in required_texts:
            if required_text not in text:
                fail(f"{path} missing P0 protocol documentation anchor: {required_text}")

    p0_skill_requirements = {
        "ds-lite-intake": ("research/work-unit.json", "claim requirement"),
        "ds-lite-scout": ("research/work-unit.json", "planning"),
        "ds-lite-idea": ("research/work-unit.json", "planning"),
        "ds-lite-experiment": ("evidence_requirements", "ds-lite.evidence.v1"),
        "ds-lite-review": ("review-result.json", "claim_assessment"),
        "ds-lite-analysis-write": ("typed review result", "supportable"),
        "ds-lite-iterate": ("claim_readiness", "evidence_detail"),
    }
    for skill_name, required_texts in p0_skill_requirements.items():
        skill_text = (plugin_root / "skills" / skill_name / "SKILL.md").read_text(encoding="utf-8")
        for required_text in required_texts:
            if required_text not in skill_text:
                fail(f"{skill_name} missing P0 behavior: {required_text}")

    long_task_protocol = plugin_root / "references" / "external-long-task-protocol.md"
    long_task_text = long_task_protocol.read_text(encoding="utf-8") if long_task_protocol.exists() else ""
    required_long_task_terms = (
        "research/artifacts/external-task-<task-id>.md",
        "research/artifacts/external-tmux-plan-<plan-id>.md",
        "runtime owner",
        "agent-ephemeral",
        "append a new attempt section",
        "Evidence Pack / run ID:",
        "Command SHA-256",
        "PID",
        "scheduler job ID",
        "Stdout / stderr / exit-code paths",
        "checkpoint",
        "heartbeat",
        "Declared budget and consumed budget",
        "Recovery command",
        "prepared / running / suspect / interrupted / recovering / completed / failed / abandoned",
        "Terminal states: `completed / failed / abandoned`",
        "Non-terminal states: `prepared / running / suspect / interrupted / recovering`",
        "An attempt process failure is not automatically a terminal task failure",
        "Each new claim-bearing launch attempt must use a new run ID and Evidence Pack",
        "## Persistence Probe",
        "## Tmux Capacity And Manual Bootstrap",
        "User bootstrap command block",
        "User bootstrap command block SHA-256:",
        "awaiting-user-bootstrap",
        "tmux server + anchor session",
        "Fixed socket path:",
        "Allowed Codex child-worker slots:",
        "Single launch authority / controller task ID:",
        "Slot claim key format and authority handoff rule:",
        "Server PID / process start time / parent PID:",
        "Host / user / UID / boot ID:",
        "Socket path / owner / mode / inode:",
        "cgroup / container / PID namespace / allocation:",
        "Before-disconnect observation:",
        "After-reconnect observation:",
        "Exact read-only query and attach commands:",
        "authorization baseline, not a second runtime state store",
        "remains authoritative for process state and attempt",
        "Only `verified` plans authorize slots",
        "plan_id + slot_id + task_id + attempt + command_hash",
        "no host-provided atomic claim exists, stop instead of racing",
        "Codex CLI child worker",
        "provider thread/task ID",
        "tested or unverified resume result",
        "tmux persistence does not prove Codex",
        "create the tmux server or top-level session",
        "fall back to `tmux new-session`",
        "recover first, resubmit last",
        "duplicate submission",
        "## Product Boundary",
        "It does not provide a daemon, queue, process supervisor, launcher,",
    )
    for term in required_long_task_terms:
        if term not in long_task_text:
            fail(f"external long-task protocol missing required term: {term}")

    for skill_name in ("ds-lite-intake", "ds-lite-experiment", "ds-lite-review", "ds-lite-iterate"):
        skill_text = (plugin_root / "skills" / skill_name / "SKILL.md").read_text(encoding="utf-8")
        if "external-long-task-protocol.md" not in skill_text:
            fail(f"{skill_name} must reference external-long-task-protocol.md")

    long_task_skill_requirements = {
        "ds-lite-intake": (
            "`prepared`, `running`, `suspect`, `interrupted`, and `recovering` task records",
            "inventory `research/artifacts/external-tmux-plan-*.md`",
            "does not prove that a workload, Codex CLI child worker, or provider conversation",
        ),
        "ds-lite-experiment": (
            "attach the external task record and linked external tmux plan",
            "Stop at `awaiting-user-bootstrap`",
            "Never create the tmux server or top-level session",
            "plan's single launch authority",
            "persist the slot claim/idempotency key",
        ),
        "ds-lite-review": (
            "follow each matching task's tmux plan/slot reference",
            "tmux capacity plan is verified",
            "launcher matched the single launch authority",
            "slot claim/idempotency key was persisted before launch",
            "separate process and provider-resume evidence",
        ),
        "ds-lite-iterate": (
            "non-terminal (`prepared`, `running`, `suspect`, `interrupted`, or `recovering`)",
            "must not create or expand tmux capacity",
            "gate state is not `verified`",
            "plan's single launch authority",
            "must not race another launcher",
        ),
    }
    for skill_name, required_texts in long_task_skill_requirements.items():
        skill_text = (plugin_root / "skills" / skill_name / "SKILL.md").read_text(encoding="utf-8")
        for required_text in required_texts:
            if required_text not in skill_text:
                fail(f"{skill_name} missing external long-task behavior: {required_text}")

    forbidden_runtime_claims = (
        "tmux guarantees persistence",
        "DS Lite automatically runs long tasks",
        "Codex conversation persistence proves process persistence",
        "tmux 保证持久",
        "Lite 自动长期运行",
        "Codex 对话存在即任务仍运行",
        "tmux server persistence proves Codex conversation recovery",
        "tmux 中的 Codex 对话一定会保留",
        "a \"subsession\" means",
        "child session\" means",
        "所谓子会话是",
        "本协议所称的“子会话”",
        "计划内的“子会话”是",
    )
    runtime_claim_surface = long_task_text + "\n" + "\n".join(
        (plugin_root / "skills" / skill_name / "SKILL.md").read_text(encoding="utf-8")
        for skill_name in ("ds-lite-intake", "ds-lite-experiment", "ds-lite-review", "ds-lite-iterate")
    )
    runtime_claim_surface += "\n" + "\n".join(
        path.read_text(encoding="utf-8")
        for path in (
            repo_root / "PROJECT.md",
            repo_root / "docs" / "openscience-worker-handoff.zh.md",
            repo_root / "docs" / "user-guide.zh.md",
            repo_root / "docs" / "implementation.zh.md",
            repo_root / "docs" / "maintainers" / "known-issues.md",
        )
    )
    for claim in forbidden_runtime_claims:
        if claim in runtime_claim_surface:
            fail(f"runtime protocol contains an overstated claim: {claim}")

    long_task_doc_requirements = {
        repo_root / "PROJECT.md": ("外部长任务管护", "tmux 容量申请"),
        repo_root / "CHANGELOG.md": ("external long-task stewardship", "manual tmux capacity handshake"),
        repo_root / "docs" / "README.md": ("external-long-task-protocol.md", "manual tmux capacity handshakes"),
        repo_root / "docs" / "openscience-worker-handoff.zh.md": (
            "external-task-<task-id>.md",
            "external-tmux-plan-<plan-id>.md",
            "唯一启动权",
            "plan_id + slot_id + task_id + attempt + command_hash",
        ),
        repo_root / "docs" / "user-guide.zh.md": ("会话恢复不等于进程恢复", "用户手动创建 tmux"),
        repo_root / "docs" / "implementation.zh.md": (
            "进程生命周期归属",
            "tmux 人工供给握手",
            "单写者",
            "plan_id + slot_id + task_id + attempt + command_hash",
        ),
        repo_root / "docs" / "maintainers" / "known-issues.md": (
            "agent-ephemeral",
            "tmux session has no parent-child hierarchy",
        ),
        repo_root / "docs" / "maintainers" / "release-checklist.md": "fixed-socket bootstrap block",
        repo_root / "docs" / "maintainers" / "release-status.zh.md": (
            "manual tmux capacity handshake remains pending release evidence",
            "pane-scoped Codex CLI child worker",
        ),
    }
    for path, required_texts in long_task_doc_requirements.items():
        path_text = path.read_text(encoding="utf-8")
        if isinstance(required_texts, str):
            required_texts = (required_texts,)
        for required_text in required_texts:
            if required_text not in path_text:
                fail(f"{path} missing external long-task documentation anchor: {required_text}")

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
