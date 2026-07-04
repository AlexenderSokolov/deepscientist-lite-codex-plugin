#!/usr/bin/env python3
"""Build small, deterministic DeepScientist Lite teaching workspaces.

The runner prepares evidence and graph states. It does not pretend to invoke
Codex skills or make scientific judgments on a student's behalf.
"""

from __future__ import annotations

import argparse
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
LABS = ("quickstart", "evidence", "branches", "route", "paths", "revision")
EVIDENCE_CASES = ("clean", "tampered", "threshold-miss")


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

    def build(self) -> None:
        self.create_workspace()
        getattr(self, f"build_{self.lab}")()
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
        }
        return "# 教师参考答案\n\n" + answers[self.lab] + "\n\n该答案只解释当前教学 fixture，不是通用科研结论。"


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
    output = args.output
    if output is None:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        output = REPO_ROOT / ".validation-tmp" / f"{args.lab}-{args.mode}-{args.case}-{stamp}"
    try:
        builder = LabBuilder(args.lab, args.mode, args.case, output)
        builder.build()
    except (LabError, OSError, subprocess.SubprocessError, ValueError, KeyError) as exc:
        print(f"lab preparation failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({"lab": args.lab, "mode": args.mode, "case": args.case, "workspace": str(output.resolve())}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
