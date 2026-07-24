#!/usr/bin/env python3
"""Build small, deterministic DeepScientist Lite teaching workspaces.

The runner prepares evidence and graph states. It does not pretend to invoke
Codex skills or make scientific judgments on a student's behalf.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


REPO_ROOT = Path(__file__).resolve().parents[1]
STATE_SCRIPT = REPO_ROOT / "plugins" / "deepscientist-lite" / "scripts" / "ds_lite_state.py"
EVIDENCE_SCRIPT = REPO_ROOT / "plugins" / "deepscientist-lite" / "scripts" / "ds_lite_evidence.py"
ITERATION_SCRIPT = REPO_ROOT / "plugins" / "deepscientist-lite" / "scripts" / "ds_lite_iteration.py"
LABS = (
    "quickstart",
    "evidence",
    "branches",
    "route",
    "paths",
    "revision",
    "action-reflection",
    "matched-pilot",
)
EVIDENCE_CASES = ("clean", "tampered", "threshold-miss")
PILOT_CASES = ("engineering-continuity", "math-counterexample", "numerical-seeds", "idea-evaluation")
PILOT_ARMS = ("plain", "scratchpad", "ds-lite")


class LabError(RuntimeError):
    pass


def write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value.rstrip() + "\n", encoding="utf-8")


def write_json(path: Path, value: Any) -> None:
    write_text(path, json.dumps(value, ensure_ascii=False, indent=2))


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


class LabBuilder:
    def __init__(self, lab: str, mode: str, case: str, output: Path) -> None:
        self.lab = lab
        self.mode = mode
        self.case = case
        self.workspace = output.resolve()
        self.project = self.workspace / "project"
        self.logs = self.workspace / "logs"
        self.command_log: list[str] = []
        self.result: dict[str, Any] = {
            "schema_version": "ds-lite.teaching-result.v1",
            "lab": lab,
            "mode": mode,
            "case": case,
        }

    def create_workspace(self) -> None:
        if self.workspace.exists():
            raise LabError(f"output already exists; choose a new path: {self.workspace}")
        self.logs.mkdir(parents=True)
        self.project.mkdir()

    def sanitized(self, value: str) -> str:
        replacements = {
            str(self.project): "<PROJECT>",
            str(self.workspace): "<LAB_WORKSPACE>",
            str(REPO_ROOT): "<REPOSITORY>",
        }
        result = value
        for source, target in replacements.items():
            result = result.replace(source, target).replace(source.replace("\\", "/"), target)
        return result

    def run_tool(
        self,
        script: Path,
        command: str,
        *args: str,
        expected: Iterable[int] = (0,),
        env: dict[str, str] | None = None,
        label: str | None = None,
    ) -> subprocess.CompletedProcess[str]:
        merged = os.environ.copy()
        merged["PYTHONUTF8"] = "1"
        merged["PYTHONDONTWRITEBYTECODE"] = "1"
        if env:
            merged.update(env)
        argv = [sys.executable, str(script), command, "--root", str(self.project), *args]
        completed = subprocess.run(
            argv,
            cwd=REPO_ROOT,
            text=True,
            encoding="utf-8",
            errors="backslashreplace",
            capture_output=True,
            env=merged,
        )
        display = " ".join(self.sanitized(item) for item in argv)
        self.command_log.append(f"$ {display}\nexit={completed.returncode}")
        if label:
            write_text(
                self.logs / f"{label}.log",
                self.sanitized((completed.stdout or "") + (completed.stderr or "")),
            )
        if completed.returncode not in set(expected):
            detail = self.sanitized((completed.stdout or "") + (completed.stderr or ""))
            raise LabError(f"unexpected exit code {completed.returncode}: {display}\n{detail}")
        return completed

    def state(self, command: str, *args: str, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        return self.run_tool(STATE_SCRIPT, command, *args, **kwargs)

    def evidence(self, command: str, *args: str, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        return self.run_tool(EVIDENCE_SCRIPT, command, *args, **kwargs)

    def iteration(self, command: str, *args: str, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        return self.run_tool(ITERATION_SCRIPT, command, *args, **kwargs)

    def init_project(self, title: str, question: str) -> None:
        title_file = self.workspace / "title.txt"
        question_file = self.workspace / "question.txt"
        write_text(title_file, title)
        write_text(question_file, question)
        self.state(
            "init",
            "--title-file",
            str(title_file),
            "--question-file",
            str(question_file),
            label="init",
        )

    def add_artifact(self, name: str, body: str) -> str:
        relative = f"research/artifacts/{name}.md"
        write_text(self.project / relative, body)
        return relative

    def add_node(
        self,
        node_id: str,
        kind: str,
        title: str,
        *,
        parent: str | None = None,
        relation: str = "next",
        status: str | None = None,
        artifact: str | None = None,
        evidence: str | None = None,
        active: bool = False,
    ) -> None:
        args = ["--id", node_id, "--kind", kind, "--title", title]
        if parent:
            args.extend(["--parent", parent, "--relation", relation])
        if status:
            args.extend(["--status", status])
        if artifact:
            args.extend(["--artifact-path", artifact])
        if evidence:
            args.extend(["--evidence-path", evidence])
        if active:
            args.append("--active")
        self.state("add-node", *args)

    def environment(self) -> Path:
        path = self.workspace / "environment.json"
        write_json(
            path,
            {
                "schema_version": "ds-lite.environment.v1",
                "python": sys.version.split()[0],
                "platform": sys.platform,
                "packages": [],
                "container": "not-applicable",
                "hardware": "teaching fixture",
                "notes": "Only allowlisted teaching metadata is recorded.",
            },
        )
        return path

    def make_contract(
        self,
        run_id: str,
        node_id: str,
        hypothesis: str,
        command: str,
        inputs: list[str],
        metrics: list[dict[str, Any]],
        outputs: list[str],
        failure: str,
    ) -> Path:
        path = self.workspace / f"contract-{run_id}.json"
        write_json(
            path,
            {
                "schema_version": "ds-lite.experiment-contract.v1",
                "run_id": run_id,
                "node_id": node_id,
                "hypothesis": hypothesis,
                "command": command,
                "cwd": ".",
                "inputs": inputs,
                "metrics": metrics,
                "seeds": [0],
                "budget": {"value": 1, "unit": "run"},
                "expected_outputs": outputs,
                "failure_interpretation": failure,
            },
        )
        return path

    def pack_run(
        self,
        run_id: str,
        contract: Path,
        metrics_path: Path,
        outputs: list[str],
        stdout: str,
        stderr: str = "",
    ) -> subprocess.CompletedProcess[str]:
        stdout_path = self.workspace / f"{run_id}.stdout.log"
        stderr_path = self.workspace / f"{run_id}.stderr.log"
        write_text(stdout_path, stdout)
        write_text(stderr_path, stderr)
        self.evidence("init", "--run-id", run_id, "--contract", str(contract))
        args = [
            "--run-id",
            run_id,
            "--exit-code",
            "0",
            "--stdout",
            str(stdout_path),
            "--stderr",
            str(stderr_path),
            "--metrics",
            str(metrics_path),
            "--environment",
            str(self.environment()),
        ]
        for output in outputs:
            args.extend(["--output", output])
        self.evidence("finalize", *args)
        return self.evidence("verify", "--run-id", run_id, "--strict", expected=(0, 1))

    def sync_status(self) -> None:
        """Project the final teaching state into STATUS.md for handoff exercises."""

        graph = read_json(self.project / "research" / "state" / "graph.json")
        active = graph["nodes"][graph["active_node_id"]]
        trace = self.state("trace", "--node", active["id"], "--mode", "progression", "--format", "json")
        active_route = [item["id"] for item in json.loads(trace.stdout)["route"]]
        route_nodes = set(active_route)
        progression_relations = {"next", "branch", "supersedes"}
        active_successors = {
            edge.get("to")
            for edge in graph.get("adjacency", {}).get(active["id"], [])
            if edge.get("relation") in progression_relations
        }
        blocked_nodes = {
            node_id
            for node_id, node in graph["nodes"].items()
            if node.get("status") == "blocked"
        }
        current_route_blockers = sorted(blocked_nodes & route_nodes)
        blocked_followups = sorted(blocked_nodes & active_successors)
        off_route_blockers = sorted(blocked_nodes - route_nodes - set(blocked_followups))
        next_actions = {
            "quickstart": "Explain the four core file roles, then ask Codex to recover the project from files.",
            "evidence": "Review the Evidence Pack without rerunning or repairing the experiment.",
            "branches": "Review A, B, and C, then select only a passing and policy-compliant route.",
            "route": "Compare progression and all-edge traces; explain why supports and rollback do not redefine the active route.",
            "paths": "Set DS_LITE_EXTERNAL_DATASET on this machine, then run strict validation.",
            "revision": "Reconstruct the stale write, reload, reconcile, and retry sequence from the saved evidence.",
            "action-reflection": "Run one probe through $ds-lite-iterate, preserve the counterexample, update the hypothesis, and finish the user report.",
        }
        def format_nodes(node_ids: list[str]) -> str:
            return ", ".join(f"`{node_id}`" for node_id in node_ids) if node_ids else "None."

        followup_prefix = ""
        if blocked_followups:
            followup_prefix = f"Resolve or explicitly supersede {format_nodes(blocked_followups)} before claim promotion. "
        summary = active.get("summary") or active["title"]
        self.result.update(
            {
                "status_active_node": active["id"],
                "status_revision": graph["revision"],
                "state_handoff": {
                    "schema_version": "ds-lite.teaching-handoff.v1",
                    "active_node_id": active["id"],
                    "active_node_kind": active["kind"],
                    "active_node_status": active["status"],
                    "revision": graph["revision"],
                    "active_route": active_route,
                    "current_route_blockers": current_route_blockers,
                    "blocked_followups": blocked_followups,
                    "off_route_blockers": off_route_blockers,
                },
            }
        )
        write_text(
            self.project / "STATUS.md",
            f"""# Status

## Current Node

- Active node: `{active['id']}`
- Stage: {active['kind']}
- Status: {active['status']}
- Revision: {graph['revision']}

## Current Summary

{summary}

## Blockers

- Current route: {format_nodes(current_route_blockers)}
- Blocked follow-ups from the active node: {format_nodes(blocked_followups)}
- Preserved off-route blocks: {format_nodes(off_route_blockers)}

## Next Action

{followup_prefix}{next_actions[self.lab]}

## Last Updated

{datetime.now(timezone.utc).date().isoformat()}
""",
        )

    def build(self) -> None:
        self.create_workspace()
        getattr(self, f"build_{self.lab.replace('-', '_')}")()
        self.sync_status()
        self.result["project"] = "project"
        write_json(self.workspace / "lab-result.json", self.result)
        write_text(self.workspace / "COMMANDS.md", "# 本次准备实际调用的命令\n\n" + "\n\n".join(self.command_log))
        if self.mode == "reference":
            write_text(self.workspace / "REFERENCE_ANSWER.md", self.reference_answer())
        write_text(self.workspace / "LAB_README.md", self.workspace_readme())

    def build_quickstart(self) -> None:
        self.init_project("第一次使用 DS Lite", "怎样让一项小研究在换会话后仍能接着做？")
        scout = self.add_artifact(
            "scout-first-question",
            """# 问题澄清\n\n我们要检查的不是模型有多聪明，而是项目状态能否从文件恢复。\n\n- 基线：只依赖聊天记录。\n- 观察项：新会话能否说清目标、证据和下一步。\n- 风险：把模板生成误当成研究已经完成。""",
        )
        idea = self.add_artifact(
            "idea-file-handoff",
            """# 候选做法\n\n先建立一个最小文件交接：PROJECT 说明长期目标，STATUS 说明眼前位置，graph 记录路线，artifact 保存本步内容。""",
        )
        self.add_node("scout-first-question", "scout", "澄清交接问题", parent="intake-root", artifact=scout, active=True)
        self.add_node("idea-file-handoff", "idea", "用文件完成跨会话交接", parent="scout-first-question", artifact=idea, active=True)
        self.result.update({"expected_active_node": "idea-file-handoff", "expected_revision": 2})

    def build_evidence(self) -> None:
        self.init_project("证据审查实验", "一次运行成功，是否就足以支持研究结论？")
        script = self.project / "run_experiment.py"
        score = 0.70 if self.case == "threshold-miss" else 0.85
        write_text(
            script,
            """from pathlib import Path\nimport json\n\nout = Path('research/results')\nout.mkdir(parents=True, exist_ok=True)\nscore = SCORE\n(out / 'metrics.json').write_text(json.dumps({'accuracy': score}) + '\\n', encoding='utf-8')\n(out / 'result.json').write_text(json.dumps({'prediction_count': 20, 'correct': round(score * 20)}) + '\\n', encoding='utf-8')\nprint(f'accuracy={score:.2f}')\n""".replace("SCORE", repr(score)),
        )
        completed = subprocess.run(
            [sys.executable, str(script)],
            cwd=self.project,
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=True,
        )
        metrics = self.project / "research" / "results" / "metrics.json"
        contract = self.make_contract(
            "evidence-demo",
            "experiment-evidence-demo",
            "The deterministic run should reach accuracy >= 0.80.",
            "python run_experiment.py",
            ["run_experiment.py"],
            [{"name": "accuracy", "direction": "max", "threshold": 0.8}],
            ["research/results/result.json"],
            "Missing files, changed hashes, or accuracy below 0.80 blocks claim promotion.",
        )
        verify = self.pack_run(
            "evidence-demo",
            contract,
            metrics,
            ["research/results/result.json"],
            completed.stdout,
            completed.stderr,
        )
        if self.case == "tampered":
            write_json(self.project / "research" / "results" / "result.json", {"prediction_count": 20, "correct": 20})
            verify = self.evidence(
                "verify", "--run-id", "evidence-demo", "--strict", expected=(1,), label="tamper-verification"
            )
        artifact = self.add_artifact(
            "experiment-evidence-demo",
            f"""# 证据审查实验\n\n- 预先阈值：accuracy >= 0.80\n- 本次场景：`{self.case}`\n- 观察值：{score:.2f}\n- 证据包：`research/evidence/evidence-demo/manifest.json`\n\n请先核对文件与契约，再决定结论能否进入分析。""",
        )
        self.add_node(
            "experiment-evidence-demo",
            "experiment",
            "检查一次实验的证据",
            parent="intake-root",
            artifact=artifact,
            evidence="research/evidence/evidence-demo/manifest.json",
            active=True,
        )
        verification = read_json(self.project / "research" / "evidence" / "evidence-demo" / "manifest.json")[
            "verification"
        ]
        expected_decision = "pass" if self.case == "clean" else "fail"
        self.result.update(
            {
                "verification_exit_code": verify.returncode,
                "verification_status": verification["status"],
                "expected_review_decision": expected_decision,
            }
        )
        if self.mode == "reference":
            self.add_reference_review(
                experiment_id="experiment-evidence-demo",
                run_id="evidence-demo",
                review_id="review-evidence-demo",
                decision=expected_decision,
                reason=(
                    "文件、哈希和阈值均符合预先契约。"
                    if expected_decision == "pass"
                    else "证据完整性或预先阈值未通过，不能提升结论。"
                ),
                add_analysis=expected_decision == "pass",
            )

    def build_action_reflection(self) -> None:
        self.init_project(
            "行动与反思实验",
            "一个看似被样例支持的字符串机制，遇到反例后应怎样更新假设并向用户负责地汇报？",
        )
        scout = self.add_artifact(
            "scout-length-observations",
            """# 可观察事实

- 样例 `ab` 与 `a-b` 在压缩重复分隔符后长度不变。
- `a--b` 尚未测量。
- 当前只允许一次标准库 probe；没有外部调用或删除授权。
""",
        )
        idea = self.add_artifact(
            "idea-length-preserved",
            """# 待检验假设

假设：把连续连字符压成一个连字符，对给定样例总是保持字符串长度。

最小判别：按固定顺序检查 `ab`、`a-b`、`a--b`，遇到第一个长度变化就停止并保留反例。
""",
        )
        alternative = self.add_artifact(
            "idea-separator-count",
            """# 保留候选

更窄的候选机制是“规范化只保持字母顺序，不保持原始长度”。本轮不执行第二个 probe。
""",
        )
        self.add_node(
            "scout-length-observations",
            "scout",
            "区分已测样例与未测输入",
            parent="intake-root",
            artifact=scout,
            active=True,
        )
        self.add_node(
            "idea-length-preserved",
            "idea",
            "压缩分隔符保持长度",
            parent="scout-length-observations",
            artifact=idea,
            active=True,
        )
        self.add_node(
            "idea-separator-count",
            "idea",
            "规范化只保持字母顺序",
            parent="scout-length-observations",
            relation="branch",
            artifact=alternative,
        )

        material = self.project / "materials" / "run_probe.py"
        write_text(
            material,
            """import argparse
import json
from pathlib import Path


def normalize(value: str) -> str:
    while '--' in value:
        value = value.replace('--', '-')
    return value


parser = argparse.ArgumentParser()
parser.add_argument('--output', required=True)
args = parser.parse_args()
observations = []
counterexample = ''
for value in ('ab', 'a-b', 'a--b'):
    normalized = normalize(value)
    preserved = len(normalized) == len(value)
    observations.append({'input': value, 'normalized': normalized, 'length_preserved': preserved})
    if not preserved:
        counterexample = value
        break
payload = {
    'schema_version': 'ds-lite.teaching-probe-result.v1',
    'hypothesis_id': 'idea-length-preserved',
    'supports_hypothesis': not counterexample,
    'counterexample': counterexample,
    'observations': observations,
}
Path(args.output).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\\n', encoding='utf-8')
print('counterexample=' + (counterexample or 'none'))
""",
        )
        action_ref = "research/artifacts/action-contract-length.json"
        action = {
            "kind": "collect-evidence",
            "summary": "Probe whether separator normalization preserves length.",
            "prediction": "All three declared examples keep their original length.",
            "falsification_condition": "Any normalized example has a different length.",
            "resource_limits": [{"dimension": "actions", "unit": "count", "value": 1}],
            "stop_condition": "Stop at the first counterexample or after three examples.",
            "extensions": {},
        }
        write_json(self.project / action_ref, action)
        write_json(
            self.workspace / "hook-cases.json",
            {
                "schema_version": "ds-lite.teaching-hook-cases.v1",
                "display_only": True,
                "cases": [
                    {"id": "read-graph", "operation": "read Graph v2", "expected": "allow"},
                    {"id": "edit-graph", "operation": "directly edit graph.json", "expected": "block"},
                    {"id": "recursive-delete", "operation": "recursive delete", "expected": "block"},
                    {"id": "create-tmux", "operation": "create tmux capacity", "expected": "block"},
                    {"id": "stop-running", "operation": "stop with running iteration", "expected": "continue-once"},
                ],
            },
        )
        self.result.update(
            {
                "expected_hypothesis_status": "untested" if self.mode == "student" else "refuted",
                "expected_probe_result": "research/artifacts/probe-result-length.json",
                "hook_cases": "hook-cases.json",
            }
        )
        if self.mode != "reference":
            return

        graph = read_json(self.project / "research" / "state" / "graph.json")
        iteration_id = "iteration-action-reflection"
        iteration_ref = f"research/iterations/{iteration_id}.json"
        self.iteration(
            "init",
            "--iteration-id",
            iteration_id,
            "--selected-skill",
            "ds-lite-experiment",
            "--action-json",
            str(self.project / action_ref),
            "--input-ref",
            "research/artifacts/idea-length-preserved.md",
            "--expected-revision",
            str(graph["revision"]),
        )
        probe_ref = "research/artifacts/probe-result-length.json"
        completed = subprocess.run(
            [sys.executable, str(material), "--output", str(self.project / probe_ref)],
            cwd=self.project,
            text=True,
            encoding="utf-8",
            errors="backslashreplace",
            capture_output=True,
        )
        if completed.returncode != 0:
            raise LabError("reference action-reflection probe failed")
        terminal_result = self.workspace / "terminal-result-action-reflection.json"
        write_json(
            terminal_result,
            {
                "status": "completed",
                "after_revision": graph["revision"],
                "output_refs": [probe_ref],
                "graph_changes": [
                    {
                        "kind": "none",
                        "subject_id": "idea-length-preserved",
                        "summary": "Preserved the refuting probe without rewriting Graph history.",
                        "extensions": {},
                    }
                ],
                "validations": [
                    {
                        "command": "python materials/run_probe.py --output research/artifacts/probe-result-length.json",
                        "status": "pass",
                        "summary": "The bounded probe found the declared falsifying example.",
                        "extensions": {},
                    }
                ],
                "stop_reason": "negative-result-preserved",
                "reflection": {
                    "observed_outcomes": ["The first length-changing input was a--b."],
                    "hypothesis_updates": [
                        {
                            "hypothesis_id": "idea-length-preserved",
                            "status": "refuted",
                            "evidence_refs": [probe_ref],
                            "summary": "Separator compression changed the observed length.",
                            "extensions": {},
                        }
                    ],
                    "expectation_gap": "Two supporting examples did not generalize to a repeated separator.",
                    "negative_results": [
                        {
                            "summary": "The universal length-preservation hypothesis failed on a--b.",
                            "evidence_refs": [probe_ref],
                            "extensions": {},
                        }
                    ],
                    "responsibility": {
                        "authorization_basis": "Reference-mode deterministic teaching fixture.",
                        "boundaries_respected": ["One standard-library probe; no external action."],
                        "unresolved_obligations": ["Test the narrower letter-order hypothesis separately."],
                        "extensions": {},
                    },
                    "learned_boundaries": ["Supporting examples do not establish a universal mechanism."],
                    "next_candidates": [
                        {
                            "hypothesis_id": "idea-separator-count",
                            "title": "Letter order survives normalization",
                            "status": "untested",
                            "minimal_test": "Compare letter sequences across one repeated-separator case.",
                            "extensions": {},
                        }
                    ],
                    "minimal_discriminating_test": "Check letter order on a--b without asserting length preservation.",
                    "extensions": {},
                },
                "user_report": {
                    "summary": "Ran one bounded probe and preserved a counterexample that refutes length preservation.",
                    "files_changed": [probe_ref, iteration_ref],
                    "validation_summary": "The standard-library probe exited 0 and recorded a--b.",
                    "failure_layer": "claim",
                    "unverified": ["The narrower letter-order hypothesis remains untested."],
                    "hypothesis_changes": ["idea-length-preserved changed from untested to refuted."],
                    "next_action": "Test the narrower letter-order hypothesis once.",
                    "decision_needed": "none",
                    "extensions": {},
                },
                "completed_at": "2026-07-17T12:00:00Z",
                "extensions": {},
            },
        )
        self.iteration(
            "finalize",
            "--path",
            iteration_ref,
            "--result-json",
            str(terminal_result),
        )
        self.iteration("verify", "--path", iteration_ref)
        self.result["reference_iteration_ref"] = iteration_ref

    def add_reference_review(
        self,
        experiment_id: str,
        run_id: str,
        review_id: str,
        decision: str,
        reason: str,
        *,
        add_analysis: bool = False,
    ) -> None:
        status = "done" if decision == "pass" else "blocked"
        artifact = self.add_artifact(
            review_id,
            f"""# 教师参考审查（不是学生作答）\n\n| 检查通道 | 结论 | 依据 |\n| --- | --- | --- |\n| 文件完整性与可复现性 | {decision} | manifest、日志与哈希 |\n| 契约和指标 | {decision} | contract 与 metrics |\n| 引用真实性 | not-applicable | 本实验没有文献主张 |\n| 方法、代码和日志一致性 | {decision} | 脚本、输出与实验说明 |\n\n## 总决定\n\n`{decision}`：{reason}\n\n这是一份参考答案，不代表独立模型或隔离执行环境。""",
        )
        self.add_node(
            review_id,
            "review",
            f"参考审查：{decision}",
            parent=experiment_id,
            status=status,
            artifact=artifact,
            evidence=f"research/evidence/{run_id}/manifest.json",
            active=decision == "pass",
        )
        if add_analysis:
            analysis_artifact = self.add_artifact(
                f"analysis-{run_id}",
                "# 教师参考分析\n\n证据包完整，且预先约定的指标通过。这个结论只适用于当前教学 fixture。",
            )
            self.add_node(
                f"analysis-{run_id}",
                "analysis",
                "基于已通过审查的分析",
                parent=review_id,
                artifact=analysis_artifact,
                active=True,
            )

    def build_branches(self) -> None:
        self.init_project("三分支路线决策", "最高分是否一定是最值得继续的路线？")
        policy_path = self.project / "research" / "policy.json"
        write_json(policy_path, {"forbidden_inputs": ["inputs/test_labels.json"], "reason": "test labels are evaluation-only"})
        inputs = self.project / "inputs"
        inputs.mkdir()
        write_json(inputs / "train.json", {"examples": 20, "split": "train"})
        write_json(inputs / "test_labels.json", {"labels": [1, 0, 1], "split": "test"})
        runner = self.project / "run_branch.py"
        write_text(
            runner,
            """from pathlib import Path
import argparse
import json

parser = argparse.ArgumentParser()
parser.add_argument('--branch', choices=('a', 'b', 'c'), required=True)
branch = parser.parse_args().branch
scores = {
    'a': {'early_score': 0.82, 'final_score': 0.68},
    'b': {'early_score': 0.76, 'final_score': 0.79},
    'c': {'early_score': 0.91, 'final_score': 0.93},
}
json.loads(Path('inputs/train.json').read_text(encoding='utf-8'))
if branch == 'c':
    json.loads(Path('inputs/test_labels.json').read_text(encoding='utf-8'))
out = Path('research/results')
out.mkdir(parents=True, exist_ok=True)
payload = scores[branch]
(out / f'branch-{branch}-metrics.json').write_text(json.dumps(payload) + '\\n', encoding='utf-8')
(out / f'branch-{branch}.json').write_text(json.dumps({'branch': branch.upper(), **payload}) + '\\n', encoding='utf-8')
print(f"branch={branch} early={payload['early_score']} final={payload['final_score']}")
""",
        )
        idea_artifact = self.add_artifact(
            "idea-compare-three-routes",
            "# 比较三条路线\n\n统一比较 early score、final score、证据完整性和输入合规性，不允许只按最高分做决定。",
        )
        self.add_node("idea-compare-three-routes", "idea", "比较三条候选路线", parent="intake-root", artifact=idea_artifact, active=True)
        branches = {
            "a": {"early_score": 0.82, "final_score": 0.68, "inputs": ["run_branch.py", "inputs/train.json"]},
            "b": {"early_score": 0.76, "final_score": 0.79, "inputs": ["run_branch.py", "inputs/train.json"]},
            "c": {
                "early_score": 0.91,
                "final_score": 0.93,
                "inputs": ["run_branch.py", "inputs/train.json", "inputs/test_labels.json"],
            },
        }
        summary: dict[str, Any] = {}
        for key, payload in branches.items():
            run_id = f"branch-{key}"
            node_id = f"experiment-{run_id}"
            result_rel = f"research/results/{run_id}.json"
            metrics_rel = f"research/results/{run_id}-metrics.json"
            completed = subprocess.run(
                [sys.executable, str(runner), "--branch", key],
                cwd=self.project,
                text=True,
                encoding="utf-8",
                errors="backslashreplace",
                capture_output=True,
                check=True,
            )
            contract = self.make_contract(
                run_id,
                node_id,
                f"Branch {key.upper()} should retain final score >= 0.75 without violating the input policy.",
                f"python run_branch.py --branch {key}",
                payload["inputs"],
                [
                    {"name": "early_score", "direction": "observe"},
                    {"name": "final_score", "direction": "max", "threshold": 0.75},
                ],
                [result_rel],
                "A threshold miss or forbidden input blocks promotion even when another score is high.",
            )
            verify = self.pack_run(
                run_id,
                contract,
                self.project / metrics_rel,
                [result_rel],
                completed.stdout,
                completed.stderr,
            )
            artifact = self.add_artifact(
                node_id,
                f"""# 分支 {key.upper()}\n\n- early score：{payload['early_score']}\n- final score：{payload['final_score']}\n- inputs：{', '.join(payload['inputs'])}\n- policy：`research/policy.json`\n\n请同时检查最终表现、证据完整性和输入合规性。""",
            )
            self.add_node(
                node_id,
                "experiment",
                f"候选分支 {key.upper()}",
                parent="idea-compare-three-routes",
                relation="branch",
                status="blocked" if key == "a" else "proposed",
                artifact=artifact,
                evidence=f"research/evidence/{run_id}/manifest.json",
            )
            summary[key] = {"verify_exit_code": verify.returncode, **payload}
        self.result.update({"branches": summary, "expected_selection": "B", "forbidden_branch": "C"})
        if self.mode == "reference":
            decisions = {
                "a": ("fail", "early score 提升，但 final score 低于预先阈值。"),
                "b": ("pass", "final score 达标，输入合规，证据完整。"),
                "c": ("fail", "分数最高，但读取了 policy 明确禁止的测试标签。"),
            }
            for key, (decision, reason) in decisions.items():
                self.add_reference_review(
                    experiment_id=f"experiment-branch-{key}",
                    run_id=f"branch-{key}",
                    review_id=f"review-branch-{key}",
                    decision=decision,
                    reason=reason,
                )
            self.state("set-active", "--node", "review-branch-b")
            artifact = self.add_artifact(
                "analysis-branch-selection",
                "# 教师参考路线选择\n\n选择 B。A 的最终表现退化；C 使用受限标签，不能因高分获得豁免。",
            )
            self.add_node(
                "analysis-branch-selection",
                "analysis",
                "选择合规且稳定的 B 路线",
                parent="review-branch-b",
                artifact=artifact,
                active=True,
            )

    def build_route(self) -> None:
        self.init_project("路线语义实验", "证据边和回滚边会不会改变当前推进路线？")
        scout = self.add_artifact("scout-route", "# 路线检查\n\n建立一条可观察的 progression route。")
        idea = self.add_artifact("idea-route", "# 路线候选\n\n保留正常推进、证据支持和回滚三种语义。")
        decision = self.add_artifact("decision-route", "# 路线决定\n\n比较 progression 与 all 模式的输出。")
        self.add_node("scout-route", "scout", "澄清路线问题", parent="intake-root", artifact=scout, active=True)
        self.add_node("idea-route", "idea", "建立候选路线", parent="scout-route", artifact=idea, active=True)
        self.add_node("decision-route", "decision", "观察路线语义", parent="idea-route", artifact=decision, active=True)
        self.state("add-edge", "--from", "intake-root", "--to", "decision-route", "--relation", "supports", "--reason", "Root context supports the decision")
        self.state("add-edge", "--from", "decision-route", "--to", "scout-route", "--relation", "rollback", "--reason", "Return here if the decision fails")
        progression = self.state("trace", "--node", "decision-route", "--mode", "progression", "--format", "json")
        all_edges = self.state("trace", "--node", "decision-route", "--mode", "all", "--format", "json")
        write_text(self.workspace / "progression-trace.json", progression.stdout)
        write_text(self.workspace / "all-edges-trace.json", all_edges.stdout)
        self.result.update(
            {
                "progression_route": read_json(self.workspace / "progression-trace.json"),
                "all_edges_route": read_json(self.workspace / "all-edges-trace.json"),
            }
        )

    def build_paths(self) -> None:
        self.init_project("路径可移植实验", "同一个研究图怎样在 Windows、WSL 和另一台机器上复用？")
        local_path = self.project / "inputs" / "中文 数据.txt"
        write_text(local_path, "portable local input")
        self.state("link-path", "--node", "intake-root", "--type", "evidence", "--path", "inputs/中文 数据.txt")
        external_root = self.workspace / "external-data"
        external_file = external_root / "观测 数据.csv"
        write_text(external_file, "step,value\n0,1.0\n1,0.8")
        absolute = self.state(
            "link-path",
            "--node",
            "intake-root",
            "--type",
            "evidence",
            "--path",
            str(external_file.resolve()),
            expected=(1,),
            label="absolute-path-rejection",
        )
        env = {"DS_LITE_EXTERNAL_DATASET": str(external_root)}
        self.state(
            "link-path",
            "--node",
            "intake-root",
            "--type",
            "evidence",
            "--path",
            "external://dataset/观测 数据.csv",
            env=env,
        )
        graph_text = (self.project / "research" / "state" / "graph.json").read_text(encoding="utf-8")
        self.result.update(
            {
                "absolute_path_exit_code": absolute.returncode,
                "external_alias": "dataset",
                "graph_contains_machine_root": str(self.workspace) in graph_text,
            }
        )

    def build_revision(self) -> None:
        self.init_project("Revision 冲突实验", "两个会话基于同一 revision 写入时会发生什么？")
        initial = read_json(self.project / "research" / "state" / "graph.json")["revision"]
        first = self.add_artifact("scout-session-a", "# 会话 A\n\nA 基于初始 revision 写入。")
        second = self.add_artifact("scout-session-b", "# 会话 B\n\nB 先用旧 revision 写入，再重新读取后重试。")
        self.state(
            "add-node",
            "--id",
            "scout-session-a",
            "--kind",
            "scout",
            "--title",
            "会话 A 的写入",
            "--parent",
            "intake-root",
            "--relation",
            "next",
            "--artifact-path",
            first,
            "--expected-revision",
            str(initial),
        )
        stale = self.state(
            "add-node",
            "--id",
            "scout-session-b",
            "--kind",
            "scout",
            "--title",
            "会话 B 的陈旧写入",
            "--parent",
            "intake-root",
            "--relation",
            "branch",
            "--artifact-path",
            second,
            "--expected-revision",
            str(initial),
            expected=(4,),
            label="stale-revision",
        )
        reloaded = read_json(self.project / "research" / "state" / "graph.json")["revision"]
        self.state(
            "add-node",
            "--id",
            "scout-session-b",
            "--kind",
            "scout",
            "--title",
            "会话 B 协调后的写入",
            "--parent",
            "intake-root",
            "--relation",
            "branch",
            "--artifact-path",
            second,
            "--expected-revision",
            str(reloaded),
        )
        final = read_json(self.project / "research" / "state" / "graph.json")["revision"]
        self.result.update(
            {
                "initial_revision": initial,
                "stale_write_exit_code": stale.returncode,
                "reloaded_revision": reloaded,
                "final_revision": final,
            }
        )

    def workspace_readme(self) -> str:
        next_step = {
            "quickstart": "打开 project/PROJECT.md、STATUS.md、RESEARCH_MAP.md 和 research/artifacts/，用自己的话说明它们分别回答什么问题。",
            "evidence": "读取 contract、manifest、metrics 和实验 artifact，再调用 $ds-lite-review；不要先看 REFERENCE_ANSWER.md。",
            "branches": "分别审查 A/B/C，写出选择理由。最高分不是自动通行证。",
            "route": "比较 progression-trace.json 与 all-edges-trace.json，解释 supports 与 rollback 的作用。",
            "paths": "检查 graph.json 中保存的是项目相对路径和 external:// 别名，而不是本机绝对根目录。",
            "revision": "查看 logs/stale-revision.log，解释为什么退出码4要求重新读取而不是强行覆盖。",
            "action-reflection": "读取假设和 action contract，调用 $ds-lite-iterate 完成一次 probe、反思、用户汇报和停止；不要开启第二个实验。",
        }[self.lab]
        return f"""# {self.lab} 教学工作区

这是由 `teaching/lab_runner.py` 生成的 `{self.mode}` 模式工作区。

## 目录

- `project/`：本次 DS Lite 项目。
- `lab-result.json`：机器可检查的预期现象，不是科研结论。
- `logs/`：故障注入或拒绝写入的输出。
- `COMMANDS.md`：准备阶段实际调用的 Graph/Evidence 命令，路径已脱敏。
- `REFERENCE_ANSWER.md`：只在 reference 模式出现。

## 下一步

{next_step}

脚本只准备确定性数据和协议状态，不会替学生调用 Codex skill，也不会替学生完成科研判断。
"""

    def reference_answer(self) -> str:
        answers = {
            "quickstart": "四类入口分别是长期目标、当前状态、研究路线和阶段记录。生成模板只是开始，不等于研究已经完成。",
            "evidence": "clean 可以进入审查通过；tampered 因哈希变化失败；threshold-miss 的文件可以完整，但预先阈值未达到，仍应阻塞结论。",
            "branches": "选择 B。A 最终退化；C 使用测试标签，违反输入政策。路线选择必须同时考虑最终表现、合规和证据。",
            "route": "progression 只沿 next、branch、supersedes。supports 是证据关系，rollback 记录返回意图；二者都不应制造 Active Route 捷径。",
            "paths": "项目内路径使用 POSIX 相对路径；项目外数据使用 external://dataset/...。Graph 不保存外部绝对根目录。",
            "revision": "会话 B 的旧 revision 写入以退出码4被拒绝。正确恢复是重读 graph、协调差异，再携带新 revision 提交。",
            "action-reflection": "反例 a--b 推翻了长度保持假设。正确结果是 refuted，并保留 probe、负结果、授权边界、用户报告和更窄的未测试候选。",
        }
        return "# 教师参考答案\n\n" + answers[self.lab] + "\n\n该答案只解释当前教学 fixture，不是通用科研结论。"


class MatchedPilotBuilder:
    def __init__(self, output: Path) -> None:
        self.workspace = output.resolve()

    def task_text(self, case_id: str) -> str:
        tasks = {
            "engineering-continuity": """# Round 1: repair the slug utility

Work only inside `materials/`. Fix `slugger.make_slug` so the existing tests pass without changing its public signature. Run `python -m unittest -v` from `materials/`, record the command and result in `ROUND_1_REPORT.md`, and stop after this round. Preserve enough explicit state for a later context restart; do not read prompts outside this arm workspace.
""",
            "math-counterexample": """# Audit a prime-valued conjecture

The supplied observations report that `n^2 + n + 41` is prime for every integer `n` from 0 through 39. Determine whether the universal claim "the expression is prime for every non-negative integer n" is justified.

Use `materials/check_conjecture.py` or an equivalent reproducible check, search at least through `n=100`, and write `REPORT.md` with the claim status, the decisive evidence, and the difference between many supporting examples and a proof. Preserve any negative result instead of smoothing it away.
""",
            "numerical-seeds": """# Audit a multi-seed simulation

Use only the Python standard library. This pilot requires WSL computation: run `materials/run_simulation_wsl.sh 2 early.json early-wsl-proof.json`, then `materials/run_simulation_wsl.sh 20 expanded.json wsl-proof.json`, through the assigned `DS-Lite-Ubuntu-24.04` distribution. Compare the early and expanded estimates for methods A and B, retain per-seed results and both WSL proof files, and write `REPORT.md` stating what is supported, inconclusive, or contradicted. Do not turn a small mean difference into a significance claim.
""",
            "idea-evaluation": """# Evaluate three research ideas

Read `materials/candidates.json` and `materials/source-packet.md`. Compare all three candidates on novelty, feasibility, evidence strength, cost, risk, and alignment. Every non-unknown novelty judgment must cite a supplied source. Cost and risk are burdens, not positive contributions to an automatic total.

Write `IDEA_DECISION.md` with a traceable decision, uncertainty, and the smallest validation experiment for each candidate. Do not invent sources or claim that the evaluation itself proves an idea works.
""",
        }
        return tasks[case_id]

    def followup_prompts(self, case_id: str) -> dict[str, str]:
        if case_id != "engineering-continuity":
            return {}
        return {
            "round-2.md": """# Round 2: changed requirement

Continue in the same arm workspace. Extend `make_slug` so Latin accents are normalized with the Python standard library and an empty result raises `ValueError`. Add focused tests, run the full suite, update the handoff artifact available to your arm, and stop.
""",
            "round-3.md": """# Round 3: context restart

Start from the files in the arm workspace, without relying on prior chat. First state the current contract, completed work, and open risk using file evidence. Then make reserved slugs `admin` and `api` return `admin-item` and `api-item`, preserve earlier behavior, run the full suite, and write `FINAL_REPORT.md` with the recovery path and validation result.
""",
        }

    def case_materials(self, case_id: str) -> dict[str, str]:
        if case_id == "engineering-continuity":
            return {
                "README.md": "# Slug utility\n\nRun `python -m unittest -v`. Modify only files in this directory.\n",
                "slugger.py": """import re


def make_slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
""",
                "test_slugger.py": """import unittest

from slugger import make_slug


class SluggerTests(unittest.TestCase):
    def test_collapses_ascii_whitespace(self) -> None:
        self.assertEqual(make_slug("Research   Notes"), "research-notes")

    def test_removes_punctuation_without_adding_a_separator(self) -> None:
        self.assertEqual(make_slug("model+audit"), "modelaudit")


if __name__ == "__main__":
    unittest.main()
""",
            }
        if case_id == "math-counterexample":
            observations = "n,value,reported_prime\n" + "\n".join(
                f"{n},{n * n + n + 41},true" for n in range(40)
            )
            return {
                "observations.csv": observations,
                "conjecture.md": "# Candidate claim\n\nFor every non-negative integer `n`, `n^2 + n + 41` is prime.\n",
                "check_conjecture.py": """import argparse
import json
from pathlib import Path


def smallest_divisor(value: int) -> int | None:
    if value < 2:
        return 1
    candidate = 2
    while candidate * candidate <= value:
        if value % candidate == 0:
            return candidate
        candidate += 1
    return None


parser = argparse.ArgumentParser()
parser.add_argument("--max-n", type=int, required=True)
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
if args.max_n < 0:
    raise SystemExit("--max-n must be non-negative")

counterexample = None
for n in range(args.max_n + 1):
    value = n * n + n + 41
    divisor = smallest_divisor(value)
    if divisor is not None:
        counterexample = {"n": n, "value": value, "smallest_divisor": divisor}
        break

payload = {"checked_through": args.max_n, "first_counterexample": counterexample}
args.output.write_text(json.dumps(payload, indent=2) + "\\n", encoding="utf-8")
print(json.dumps(payload))
""",
            }
        if case_id == "numerical-seeds":
            return {
                "study-contract.md": """# Simulation contract

- Method A generating mean: 0.55.
- Method B generating mean: 0.53.
- Each seed uses 12 noisy observations per method.
- First inspect 2 seeds, then expand to at least 20.
- Report per-seed values and uncertainty; no significance test is pre-registered.
""",
                "run_simulation.py": """import argparse
import json
import random
from pathlib import Path


parser = argparse.ArgumentParser()
parser.add_argument("--seed-count", type=int, required=True)
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
if args.seed_count < 1:
    raise SystemExit("--seed-count must be positive")

rows = []
for seed in range(args.seed_count):
    rng = random.Random(seed)
    method_a = sum(rng.gauss(0.55, 0.20) for _ in range(12)) / 12
    method_b = sum(rng.gauss(0.53, 0.20) for _ in range(12)) / 12
    rows.append({"seed": seed, "method_a": method_a, "method_b": method_b, "difference_a_minus_b": method_a - method_b})

payload = {
    "seed_count": args.seed_count,
    "mean_a": sum(row["method_a"] for row in rows) / args.seed_count,
    "mean_b": sum(row["method_b"] for row in rows) / args.seed_count,
    "rows": rows,
}
args.output.write_text(json.dumps(payload, indent=2) + "\\n", encoding="utf-8")
print(json.dumps({key: value for key, value in payload.items() if key != "rows"}))
""",
                "run_simulation_wsl.sh": """#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 3 ]]; then
  echo "usage: run_simulation_wsl.sh SEED_COUNT OUTPUT_REF PROOF_REF" >&2
  exit 2
fi
if [[ -z "${WSL_DISTRO_NAME:-}" ]]; then
  echo "this wrapper must run inside WSL" >&2
  exit 3
fi

SEED_COUNT="$1"
OUTPUT_REF="$2"
PROOF_REF="$3"
for value in "$OUTPUT_REF" "$PROOF_REF"; do
  if [[ "$value" = /* || "$value" = *".."* || "$value" = *\\* ]]; then
    echo "output and proof refs must be relative POSIX paths" >&2
    exit 4
  fi
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ARM_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ARM_ROOT"
python3 materials/run_simulation.py --seed-count "$SEED_COUNT" --output "$OUTPUT_REF"
python3 - "$PROOF_REF" "$SEED_COUNT" "$OUTPUT_REF" <<'PY'
import json
import os
import platform
import sys
from pathlib import Path

proof_ref, seed_count, output_ref = sys.argv[1:]
payload = {
    "schema_version": "ds-lite.wsl-computation-proof.v1",
    "distribution": os.environ.get("WSL_DISTRO_NAME", "unknown"),
    "kernel": platform.system(),
    "seed_count": int(seed_count),
    "output_ref": output_ref,
    "execution": "wsl-proof",
}
Path(proof_ref).write_text(json.dumps(payload, indent=2) + "\\n", encoding="utf-8")
PY
""",
            }
        if case_id == "idea-evaluation":
            return {
                "candidates.json": json.dumps(
                    {
                        "candidates": [
                            {
                                "id": "idea-a",
                                "title": "Failure ledger for interrupted research tasks",
                                "proposal": "Keep compact, typed records of failed attempts and their repair conditions.",
                            },
                            {
                                "id": "idea-b",
                                "title": "Cross-seed review sentinel",
                                "proposal": "Require a review checkpoint when early seed rankings reverse after expansion.",
                            },
                            {
                                "id": "idea-c",
                                "title": "Single weighted innovation score",
                                "proposal": "Collapse novelty, feasibility, evidence, cost, risk, and alignment into one automatic total.",
                            },
                        ]
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                "source-packet.md": """# Fixed source packet

## S1: continuity observation

Interrupted engineering work often repeats failed attempts when the failure condition is not preserved. This packet does not establish how large that effect is.

## S2: seed sensitivity observation

Small seed sets can reverse method rankings after expansion. A review gate can expose the reversal, but this packet supplies no evidence that a specific gate improves final task quality.

## S3: multi-criteria decision warning

Cost and risk scores describe burden. Treating larger burdens as positive terms in a naive total can invert a decision.

## S4: prior-art boundary

Research logs, experiment tracking, and multi-criteria scorecards already exist as broad ideas. Novelty claims therefore require a narrower mechanism and a direct comparison, neither of which is supplied here.
""",
            }
        raise LabError(f"unknown matched pilot case: {case_id}")

    def write_shared_case(self, case_id: str) -> None:
        for name, content in self.followup_prompts(case_id).items():
            write_text(self.workspace / "prompts" / case_id / name, content)

    def input_digest(self, case_id: str, materials: dict[str, str]) -> str:
        payload = {
            "task": self.task_text(case_id),
            "followup_prompts": self.followup_prompts(case_id),
            "materials": materials,
        }
        canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def arm_instructions(self, arm_id: str) -> str:
        instructions = {
            "plain": """# Plain Codex arm

Use only files below this arm workspace. Do not use DeepScientist Lite, a persistent scratchpad, or files from another arm. You may write only the deliverables and code/tests requested by `TASK.md`. Stop at each requested checkpoint.
""",
            "scratchpad": """# Scratchpad arm

Use only files below this arm workspace. Do not use DeepScientist Lite. `NOTES.md` is the only persistent coordination aid beyond requested deliverables and code/tests; keep it concise and do not store full conversation text or private reasoning. Stop at each requested checkpoint.
""",
            "ds-lite": """# DeepScientist Lite arm

Use only files below this arm workspace. Use PROJECT, STATUS, Graph, work unit, and explicit artifacts for continuity; do not edit `graph.json` directly. Run one bounded action at a time and stop at checkpoints. Do not delegate subagents. Factor Cards are decision artifacts, not evidence, and are appropriate only for the idea-evaluation case.
""",
        }
        return instructions[arm_id]

    def write_teaching_guides(self) -> None:
        write_text(
            self.workspace / "PILOT_README.md",
            """# DeepScientist Lite matched-control pilot

This package prepares four cases across three arms: plain Codex, Codex with one `NOTES.md`, and a DeepScientist Lite workspace. All 12 runs are `pending`; no model task has been executed, scored, or compared.

## Layout

- `arms/<case>/<arm>/`: isolated student workspaces.
- `prompts/engineering-continuity/`: round 2 and round 3 prompts, delivered only after the prior checkpoint.
- `STUDENT_GUIDE.zh.md`: participant commands and deliverables.
- `INSTRUCTOR_GUIDE.zh.md`: preregistration, isolation, scoring, and interpretation.
- `RUBRIC.csv`: metric definitions.
- `results/`: empty scoring surface marked `prepared-not-run`.

Use a host sandbox or copy one arm into a separate execution root before opening it. Changing the current directory alone is not access control and does not hide sibling arms or instructor files. The pilot is descriptive teaching evidence, not a domain-support or statistical-significance claim.
""",
        )
        write_text(
            self.workspace / "STUDENT_GUIDE.zh.md",
            """# 学生指南：四案例三组对照

## 共同规则

每次只打开一个 `arms/<case>/<arm>/` 作为工作区。先读 `ARM_INSTRUCTIONS.md`，再读 `TASK.md`。不得查看兄弟 arm、教师材料或根目录评分文件；不得保存完整对话、隐藏推理、凭据或本机绝对根目录。所有判断都要落到请求的产物中。

## Windows PowerShell

```powershell
Set-Location arms/numerical-seeds/plain
python materials/run_simulation.py --seed-count 2 --output early.json
python materials/run_simulation.py --seed-count 20 --output expanded.json
```

工程案例每轮结束后停止。教师随后单独提供 `round-2.md`；第二轮结束并更换上下文后，再提供 `round-3.md`。

## Git Bash / WSL

```bash
cd arms/numerical-seeds/plain
python3 materials/run_simulation.py --seed-count 2 --output early.json
python3 materials/run_simulation.py --seed-count 20 --output expanded.json
```

WSL 中只使用当前 arm 的相对路径。不要为课程创建 tmux、后台 worker 或自动重试循环。

## 交付边界

- 工程：代码、测试、每轮报告与最终恢复说明。
- 数学：可复核搜索结果与 `REPORT.md`；支持样例不是证明。
- 数值：2 seed 和扩展 seed 的机器结果、逐 seed 记录与谨慎解释。
- 创新评价：六维比较、来源引用、不确定性和最小验证实验。

课程不会提供预填答案。脚本运行成功也不等于科研主张成立。
""",
        )
        write_text(
            self.workspace / "INSTRUCTOR_GUIDE.zh.md",
            """# 教师材料：执行、盲评与结果解读

## 执行前预注册

在真实运行前固定并记录准确模型版本、共同提示词、每轮预算、允许工具、材料摘要、超时规则和停止条件。任何字段仍为 `pending-operator-input` 时不得开始比较。真实 12-arm Codex 调用和任何子智能体 forward test 都需要用户明确授权；本包不会自行发起。

## 隔离与投递

1. 为每个 manifest run 创建独立任务，并用宿主 sandbox 或独立执行副本只暴露对应 arm。仅切换当前目录不是访问控制。
2. plain 不使用持久 scratchpad；scratchpad 只使用 `NOTES.md`；ds-lite 使用已初始化的文件协议。
3. 工程案例按三轮投递。第二轮结束后新建上下文，再投递第三轮，计时从第三轮提示出现开始。
4. 其他案例只投递 `TASK.md`。数值案例在 Windows 或 WSL 中真实执行标准库脚本。
5. 保存脱敏后的命令、最终产物、验证退出码和成本；不保存完整对话或隐藏推理。

## 评分

用 `RUBRIC.csv` 的统一定义评分，最好先隐藏 arm 标签。正确率和恢复时间之外，还要检查重复工作、状态遗漏、负结果保留、证据可追溯、路线恢复、artifact 碎片、speculation leakage、成本和单位成本信息增益。碎片率必须结合“能否从权威入口恢复”解释，不能单纯按文件数量惩罚 DS Lite。

## 答案边界

教师可以核对可执行事实，但不得把参考现象提前放进 arm。数学案例存在可计算的反例；数值案例刻意让极小 seed 子集产生误导，扩展结果仍需按不确定性解释；创新案例没有预设唯一赢家。工程案例以测试、需求保持和跨上下文恢复为准。

## 结果解读

这是 4 案例 x 3 arm 的 pilot，只报告描述性差异，不作统计显著性宣称。单次教学运行不能把 literature、mathematical、software 或 numerical profile 从 `reserved / not-validated` 升级，也不能证明 DeepScientist Lite 在一般办公任务上有效。Finance Factor 不进入这些 core 教学默认值。
""",
        )
        write_text(
            self.workspace / "RUBRIC.csv",
            """metric,type,collection_rule,interpretation_boundary
task_correctness,score_0_4,Apply case-specific tests or evidence checks,Correct output without preserved evidence is not full credit
recovery_time_seconds,nonnegative_number,Measure from restart prompt to an evidence-backed state summary,Use the same timer rule for all arms
repeated_work_count,count,Count repeated actions already evidenced as complete,Do not count deliberate revalidation
state_omission_count,count,Count required contract or status facts absent at handoff,Score only facts available before restart
negative_result_retained,binary_or_na,Check whether counterexamples reversals and failed attempts remain visible,Retention does not make a claim supportable
evidence_traceability,score_0_4,Trace claims to commands outputs sources or typed refs,Fluent prose alone receives no evidence credit
route_recovery,score_0_4,Reconstruct current state next action and rollback condition,Do not reward guessed history
artifact_fragmentation,ratio,Count unreferenced deliverable fragments over all deliverable fragments,File count alone is not fragmentation
speculation_leakage,count,Count unsupported claims presented as established,Unknown or explicitly provisional statements are not leakage
cost_units,nonnegative_number,Record the same provider-defined cost unit for every arm,Do not mix incomparable units
information_gain_per_cost,derived,Divide rubric-approved information gain by cost units,Leave blank when cost is unavailable or zero
""",
        )

    def write_results_scaffold(self) -> None:
        write_text(
            self.workspace / "results" / "README.md",
            """# Pilot results

Status: `prepared-not-run`.

No Codex arm has been executed or scored. Fill the CSV only from saved, redacted artifacts after all arms use the same model, prompt sequence, budget, tools, and materials. A 12-arm pilot is descriptive and does not establish statistical significance or validate a reserved domain profile.
""",
        )
        write_text(
            self.workspace / "results" / "scores.csv",
            "case,arm,status,task_correctness,recovery_time_seconds,repeated_work_count,state_omission_count,negative_result_retained,evidence_traceability,route_recovery,artifact_fragmentation,speculation_leakage,cost_units,information_gain_per_cost,notes",
        )

    def init_ds_lite_arm(self, arm: Path, case_id: str) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                str(STATE_SCRIPT),
                "init",
                "--root",
                str(arm),
                "--title",
                f"Matched pilot: {case_id}",
                "--question",
                f"Complete the bounded {case_id} teaching task and preserve an auditable handoff.",
            ],
            cwd=REPO_ROOT,
            text=True,
            encoding="utf-8",
            errors="backslashreplace",
            capture_output=True,
            env={**os.environ, "PYTHONUTF8": "1", "PYTHONDONTWRITEBYTECODE": "1"},
        )
        if completed.returncode != 0:
            raise LabError(f"DS Lite arm initialization failed for {case_id}: {completed.stdout}{completed.stderr}")

    def build(self) -> None:
        if self.workspace.exists():
            raise LabError(f"output already exists; choose a new path: {self.workspace}")
        self.workspace.mkdir(parents=True)
        runs = []
        for case_id in PILOT_CASES:
            self.write_shared_case(case_id)
            materials = self.case_materials(case_id)
            digest = self.input_digest(case_id, materials)
            for arm_id in PILOT_ARMS:
                arm = self.workspace / "arms" / case_id / arm_id
                write_text(arm / "TASK.md", self.task_text(case_id))
                write_text(arm / "ARM_INSTRUCTIONS.md", self.arm_instructions(arm_id))
                for relative, content in materials.items():
                    write_text(arm / "materials" / relative, content)
                if arm_id == "scratchpad":
                    write_text(arm / "NOTES.md", "# Notes\n\n")
                elif arm_id == "ds-lite":
                    self.init_ds_lite_arm(arm, case_id)
                run_id = f"{case_id}--{arm_id}"
                prompt_refs = [f"arms/{case_id}/{arm_id}/TASK.md"]
                prompt_refs.extend(f"prompts/{case_id}/{name}" for name in self.followup_prompts(case_id))
                runs.append(
                    {
                        "run_id": run_id,
                        "case": case_id,
                        "arm": arm_id,
                        "status": "pending",
                        "workspace": f"arms/{case_id}/{arm_id}",
                        "prompt_refs": prompt_refs,
                        "input_digest": digest,
                        "result_ref": f"results/{run_id}.json",
                    }
                )
        self.write_teaching_guides()
        self.write_results_scaffold()
        write_json(
            self.workspace / "pilot-manifest.json",
            {
                "format_version": "ds-lite.matched-pilot.v1",
                "status": "prepared-not-run",
                "cases": list(PILOT_CASES),
                "arms": list(PILOT_ARMS),
                "control_policy": {
                    "model": "pending-operator-input",
                    "prompt_budget": "pending-operator-input",
                    "tool_policy": "pending-operator-input",
                    "material_digest_algorithm": "sha256",
                    "actual_execution_authorization": "required",
                },
                "runs": runs,
            },
        )


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Prepare runnable DeepScientist Lite teaching labs.")
    result.add_argument("--lab", choices=LABS, required=True)
    result.add_argument("--mode", choices=("student", "reference"), default="student")
    result.add_argument("--case", choices=EVIDENCE_CASES, default="clean")
    result.add_argument("--output", type=Path)
    return result


def main() -> int:
    args = parser().parse_args()
    if args.lab != "evidence" and args.case != "clean":
        print("--case is only meaningful for the evidence lab", file=sys.stderr)
        return 1
    if args.lab == "matched-pilot" and args.mode != "student":
        print("matched-pilot creates student workspaces; instructor materials are generated separately", file=sys.stderr)
        return 1
    output = args.output
    if output is None:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        output = REPO_ROOT / ".validation-tmp" / f"{args.lab}-{args.mode}-{args.case}-{stamp}"
    try:
        builder = MatchedPilotBuilder(output) if args.lab == "matched-pilot" else LabBuilder(args.lab, args.mode, args.case, output)
        builder.build()
    except (LabError, OSError, subprocess.SubprocessError, ValueError, KeyError) as exc:
        print(f"lab preparation failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({"lab": args.lab, "mode": args.mode, "case": args.case, "workspace": str(output.resolve())}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
