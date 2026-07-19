#!/usr/bin/env python3
"""Prepare a fresh, isolated Codex acceptance package.

This command copies the plugin and creates deterministic teaching fixtures. It
does not register a marketplace, install a plugin, or modify Codex user state.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "ds-lite.codex-acceptance.v1"
PLUGIN_NAME = "deepscientist-lite"
SAFE_NAME = re.compile(r"^[a-z][a-z0-9.-]*$")


class PreparationError(RuntimeError):
    pass


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value.rstrip() + "\n", encoding="utf-8")


def write_communication_fixture(output: Path) -> dict[str, Any]:
    """Write fixed, anonymous A/B prompts outside the copied runtime plugin."""
    cases = [
        {
            "id": "simple-answer", "task_class": "settled-answer", "profile": "research-peer",
            "detail_mode": "concise", "language": "zh",
            "prompt": "项目约定已经明确：STYLE.md 是可选的沟通合同，缺失时回退到 research-peer。请直接回答这个封闭问题：旧项目没有 STYLE.md 时，ds-lite-intake 会不会静默创建它？请用一小段自然中文回答，给出规则依据；没有必要展开实现过程，但不得把‘提示创建’说成‘已经创建’。",
            "expected_protected": ["STYLE.md", "research-peer", "ds-lite-intake"],
            "expected_semantic_fields": ["answer", "rule basis", "scope"],
        },
        {
            "id": "complex-process", "task_class": "repository-change", "profile": "research-peer",
            "detail_mode": "deep", "language": "zh",
            "prompt": "请把下面这次仓库修改整理成可审计交付说明。已读取 PROJECT.md、plugins/deepscientist-lite/scripts/ds_lite_state.py；已修改 tests/test_state_kernel.py；运行 python -m pytest tests/test_state_kernel.py -q，结果 48 passed；没有运行 PowerShell 验证，也没有做真实宿主安装。说明目标、实际读取、实际修改、验证结果、未验证项、限制和下一步，不要把源码测试写成宿主验收。",
            "expected_protected": ["PROJECT.md", "plugins/deepscientist-lite/scripts/ds_lite_state.py", "tests/test_state_kernel.py", "python -m pytest tests/test_state_kernel.py -q", "48 passed"],
            "expected_semantic_fields": ["goal", "inspected", "changed", "verification", "limitations", "next step"],
        },
        {
            "id": "blocked-task", "task_class": "blocked-execution", "profile": "compact-operator",
            "detail_mode": "adaptive", "language": "zh",
            "prompt": "任务是运行 GPU 基线，但当前机器没有授权的 CUDA 设备。实际执行 nvidia-smi，退出码为 1，stderr 为 NVIDIA-SMI has failed；没有启动训练，也没有生成 metrics.json。请给出面向用户的阻塞汇报：说明尝试、证据、当前安全状态、不能继续的原因和所需决策。禁止写‘基线已完成’或虚构性能数字。",
            "expected_protected": ["nvidia-smi", "1", "NVIDIA-SMI has failed", "metrics.json"],
            "expected_semantic_fields": ["blocker", "attempt", "evidence", "safe state", "required decision"],
        },
        {
            "id": "polish-zh", "task_class": "academic-rewrite", "profile": "research-peer",
            "detail_mode": "adaptive", "language": "zh",
            "prompt": "请深度润色下面这段生硬中文，使其更像科研同行之间的自然说明，并附简短变更报告。原文：‘值得注意的是，本研究进行了一个全面的实验评估。实验结果清楚地表明，我们所提出的方法在三个数据集上均实现了显著的性能提升。进一步而言，这一发现不仅验证了框架的有效性，而且为未来研究提供了重要启示。’不要增加数据、文献、因果解释或宏大意义；保留‘三个数据集’这一事实强度。",
            "expected_protected": ["三个数据集"],
            "expected_semantic_fields": ["rewritten text", "change report", "no new claim", "protected-content confirmation"],
        },
        {
            "id": "polish-en", "task_class": "academic-rewrite", "profile": "research-peer",
            "detail_mode": "adaptive", "language": "en",
            "prompt": "Rewrite the following stiff paragraph as restrained peer-facing research prose, then provide a compact change report: ‘It is important to note that our novel and robust framework serves as a pivotal step toward unlocking the full potential of data-driven discovery. Moreover, the results clearly demonstrate its significant impact across a diverse range of settings.’ Do not invent a dataset, metric, citation, causal mechanism, or broader societal benefit. Preserve the fact that the evidence covers only the evaluated settings.",
            "expected_protected": ["evaluated settings"],
            "expected_semantic_fields": ["rewritten text", "change report", "evidence-strength calibration", "no invented evidence"],
        },
        {
            "id": "academic-numbers", "task_class": "academic-rewrite", "profile": "research-peer",
            "detail_mode": "deep", "language": "en",
            "prompt": "Polish this result paragraph without changing any number, unit, comparison, or statistical qualifier, and report the preservation check: ‘Macro-F1 increased from 71.4% to 73.2% on the held-out set (n = 480), while median latency increased from 12.5 ms to 14.1 ms. The paired test gave p = 0.031, which is below the prespecified 0.05 threshold.’ Do not call the latency trade-off negligible and do not strengthen association into causation.",
            "expected_protected": ["71.4%", "73.2%", "n = 480", "12.5 ms", "14.1 ms", "p = 0.031", "0.05"],
            "expected_semantic_fields": ["rewritten text", "trade-off", "change report", "number preservation"],
        },
        {
            "id": "academic-citations", "task_class": "academic-rewrite", "profile": "research-peer",
            "detail_mode": "deep", "language": "en",
            "prompt": "Revise the paragraph for clarity while preserving every citation key and qualifier: ‘Prior work suggests that retrieval augmentation may improve factual consistency in some domains [@smith2024; @lee2025]. However, evidence for long-horizon scientific planning remains limited [@garcia2023]. Our pilot observations are consistent with, but do not establish, a benefit.’ Keep may, some domains, remains limited, and do not establish. Include a change report and a citation-key preservation confirmation.",
            "expected_protected": ["[@smith2024; @lee2025]", "[@garcia2023]", "may", "some domains", "remains limited", "do not establish"],
            "expected_semantic_fields": ["rewritten text", "qualifier preservation", "citation preservation", "change report"],
        },
        {
            "id": "profile-peer", "task_class": "diagnosis", "profile": "research-peer",
            "detail_mode": "adaptive", "language": "zh",
            "prompt": "请以 research-peer 风格解释这个诊断结论：同一配置下，早期预算的 validation AUC 上升，但最终预算的 test accuracy 下降；目前只有 run-017 的 metrics.json 和 stderr.log，没有第二个 seed。请区分观察事实、可能解释和缺失证据，说明为什么现在不能宣布方法更优，并给出最小的判别性复查。",
            "expected_protected": ["research-peer", "validation AUC", "test accuracy", "run-017", "metrics.json", "stderr.log", "seed"],
            "expected_semantic_fields": ["observation", "hypotheses", "missing evidence", "discriminator", "next check"],
        },
        {
            "id": "profile-teaching", "task_class": "settled-answer", "profile": "teaching-explainer",
            "detail_mode": "deep", "language": "zh",
            "prompt": "请用 teaching-explainer 模板向第一次接触科研工程的学生解释：为什么‘生成了 artifact’不等于‘实验取得进展’？需要解释 artifact、Evidence Pack 和通过 review 的区别，给一个可观察的例子，再说明这个规则的限制。不要使用口号式结尾，也不要假设学生已经理解 Graph v2。",
            "expected_protected": ["teaching-explainer", "artifact", "Evidence Pack", "review", "Graph v2"],
            "expected_semantic_fields": ["plain answer", "terms", "mechanism", "example", "limitation"],
        },
        {
            "id": "profile-operator", "task_class": "repository-change", "profile": "compact-operator",
            "detail_mode": "concise", "language": "zh",
            "prompt": "请用 compact-operator 模板交付以下事实：已修改 plugins/deepscientist-lite/hooks/hooks.json；python -m py_compile plugins/deepscientist-lite/scripts/ds_lite_hook.py 返回 0；tests/test_communication_hook.py 尚未运行；当前阻塞是宿主 hook 格式未确认。输出要短，但必须保留动作、证据、结果、阻塞和下一步，不能把 py_compile 写成功能测试。",
            "expected_protected": ["compact-operator", "plugins/deepscientist-lite/hooks/hooks.json", "python -m py_compile plugins/deepscientist-lite/scripts/ds_lite_hook.py", "0", "tests/test_communication_hook.py"],
            "expected_semantic_fields": ["action", "evidence", "result", "blocker", "next step"],
        },
        {
            "id": "profile-reflective", "task_class": "methodological-reflection", "profile": "reflective-researcher",
            "detail_mode": "deep", "language": "zh",
            "prompt": "请以 reflective-researcher 风格反思这个试验：假设是加入检索能降低事实错误；单次 pilot 的错误率从 8.0% 降到 6.5%，但样本仅 200 条，标注者知道实验条件。讨论前提、可证伪性、可能的确认偏差、不确定性、失败结果会改变什么，以及下一项测试。哲学思考只能服务方法论，不能引用名人或把一次 pilot 提升为普遍规律。",
            "expected_protected": ["reflective-researcher", "8.0%", "6.5%", "200"],
            "expected_semantic_fields": ["assumptions", "falsifiability", "bias", "uncertainty", "failure meaning", "next test"],
        },
        {
            "id": "custom-protection", "task_class": "repository-change", "profile": "custom",
            "detail_mode": "deep", "language": "zh",
            "prompt": "采用自定义风格：语气自然、允许一句方法论反思，但不要改动下面 JSON 与命令。请解释这次配置变更的过程、验证、限制和下一步。JSON：\n```json\n{\"seed\": 42, \"metric\": \"macro-F1\", \"threshold\": 0.875}\n```\n命令：python run_eval.py --config \"configs/base zh.json\" --seed 42。当前只完成配置审读，命令尚未运行，因此不得声称已验证结果。",
            "expected_protected": ["{\"seed\": 42, \"metric\": \"macro-F1\", \"threshold\": 0.875}", "python run_eval.py --config \"configs/base zh.json\" --seed 42"],
            "expected_semantic_fields": ["process", "verification status", "limitations", "methodological reflection", "next step"],
        },
    ]
    case_ids = [case["id"] for case in cases]
    communication_root = output / "communication"
    write_json(
        communication_root / "cases.json",
        {
            "schema_version": "ds-lite.communication-fixture.v1",
            "runtime_loaded": False,
            "cases": cases,
            "scoring_dimensions": ["naturalness", "clarity", "process_transparency", "evidence_discipline", "information_density"],
            "acceptance_bar": "12/12 preserve correctness and evidence discipline; at least 8/12 strictly improve naturalness or clarity.",
        },
    )
    write_text(
        communication_root / "BLIND_AB_SCORECARD.md",
        """# Blind A/B Scorecard\n\nDo not record model identity in the score. Compare old and new outputs for each fixed case.\n\n| Case | Naturalness (1-5) | Clarity (1-5) | Process transparency (1-5) | Evidence discipline (1-5) | Information density (1-5) | Correctness preserved? | Better: A/B/tie | Notes |\n| --- | ---: | ---: | ---: | ---: | ---: | --- | --- | --- |\n| simple-answer | | | | | | | | |\n| complex-process | | | | | | | | |\n| blocked-task | | | | | | | | |\n| polish-zh | | | | | | | | |\n| polish-en | | | | | | | |\n| academic-numbers | | | | | | | | |\n| academic-citations | | | | | | | |\n| profile-peer | | | | | | | |\n| profile-teaching | | | | | | | |\n| profile-operator | | | | | | | |\n| profile-reflective | | | | | | | |\n| custom-protection | | | | | | | |\n\nAcceptance: no correctness or evidence-discipline regression in any case; at least 8 cases strictly improve naturalness or clarity.\n""",
    )
    return {
        "path": "communication",
        "case_ids": case_ids,
        "runtime_loaded": False,
        "scorecard": "communication/BLIND_AB_SCORECARD.md",
    }


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def git_head(repo_root: Path) -> str | None:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_root,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
    )
    return completed.stdout.strip() if completed.returncode == 0 else None


def acceptance_version(release_version: str, cachebuster: str) -> str:
    if not SAFE_NAME.fullmatch(cachebuster):
        raise PreparationError("cachebuster must start with a letter and contain only lowercase letters, digits, dots, or hyphens")
    public_version = release_version.split("+", 1)[0]
    return f"{public_version}+codex.{cachebuster}"


def run_lab(repo_root: Path, output: Path, lab: str, case: str = "clean") -> None:
    command = [
        sys.executable,
        str(repo_root / "teaching" / "lab_runner.py"),
        "--lab",
        lab,
        "--mode",
        "student",
        "--case",
        case,
        "--output",
        str(output),
    ]
    completed = subprocess.run(
        command,
        cwd=repo_root,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
    )
    if completed.returncode != 0:
        detail = (completed.stdout + completed.stderr).strip()
        raise PreparationError(f"failed to prepare {lab}/{case}: {detail}")


def manual_guide(marketplace_name: str, version: str) -> str:
    return f"""# Codex 人工验收入口

此目录是隔离副本，不会自动修改 Codex 配置。副本版本为 `{version}`。

## 安装边界

1. 在 Codex CLI 中执行 `codex plugin marketplace add <此目录>`，只添加 marketplace 来源。
2. 重启 Codex，在 `/plugins` 中选择 `{marketplace_name}`，再安装 `deepscientist-lite`。
3. 新建线程，确认界面显示副本版本，并能发现七个技能。

“marketplace 已添加”不等于“插件已安装”。如果当前 Codex 构建没有 `/plugins` 或相应插件浏览能力，记录为宿主能力缺失，不要删除旧缓存或伪造安装成功。

## 建议执行顺序

- `projects/manual-main/`：从零测试 intake → scout → idea → experiment → review → analysis，并额外触发一次 `$ds-lite-iterate`。
- `fixtures/evidence-clean/`、`evidence-tampered/`、`evidence-threshold-miss/`：分别测试通过、哈希篡改和阈值失败。
- `fixtures/branches/`：检查 A 退化、B 稳定、C 标签泄漏三条路线。
- `fixtures/route/`、`paths/`、`revision/`：检查路线、路径和 revision 协议。

每个线程都记录提示词、线程标识、实际文件证据和判定；线程失败但没有产生文件时，归类为宿主基础设施问题，不归咎于插件协议。
"""


def prepare(repo_root: Path, output: Path, cachebuster: str, marketplace_name: str, with_fixtures: bool) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    output = output.resolve()
    if output.exists():
        raise PreparationError(f"output already exists; choose a fresh path: {output}")
    if not SAFE_NAME.fullmatch(marketplace_name):
        raise PreparationError("marketplace name must start with a letter and contain only lowercase letters, digits, dots, or hyphens")

    source_plugin = repo_root / "plugins" / PLUGIN_NAME
    source_manifest = source_plugin / ".codex-plugin" / "plugin.json"
    marketplace_source = repo_root / ".agents" / "plugins" / "marketplace.json"
    lab_runner = repo_root / "teaching" / "lab_runner.py"
    for required in (source_manifest, marketplace_source, lab_runner):
        if not required.exists():
            raise PreparationError(f"required source file is missing: {required}")

    output.parent.mkdir(parents=True, exist_ok=True)
    output.mkdir()
    copied_plugin = output / "plugins" / PLUGIN_NAME
    shutil.copytree(
        source_plugin,
        copied_plugin,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )

    plugin_manifest = read_json(copied_plugin / ".codex-plugin" / "plugin.json")
    release_version = str(plugin_manifest["version"])
    version = acceptance_version(release_version, cachebuster)
    plugin_manifest["version"] = version
    write_json(copied_plugin / ".codex-plugin" / "plugin.json", plugin_manifest)

    marketplace = read_json(marketplace_source)
    marketplace["name"] = marketplace_name
    interface = marketplace.setdefault("interface", {})
    interface["displayName"] = f"DeepScientist Lite acceptance ({cachebuster})"
    write_json(output / ".agents" / "plugins" / "marketplace.json", marketplace)

    fixture_specs = [
        ("evidence-clean", "evidence", "clean"),
        ("evidence-tampered", "evidence", "tampered"),
        ("evidence-threshold-miss", "evidence", "threshold-miss"),
        ("branches", "branches", "clean"),
        ("route", "route", "clean"),
        ("paths", "paths", "clean"),
        ("revision", "revision", "clean"),
    ]
    fixture_paths: list[str] = []
    communication_fixture: dict[str, Any] | None = None
    if with_fixtures:
        for directory, lab, case in fixture_specs:
            destination = output / "fixtures" / directory
            run_lab(repo_root, destination, lab, case)
            fixture_paths.append(destination.relative_to(output).as_posix())
        communication_fixture = write_communication_fixture(output)
    (output / "projects" / "manual-main").mkdir(parents=True)

    record: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source": {
            "repository": str(repo_root),
            "git_head": git_head(repo_root),
            "release_version": release_version,
        },
        "marketplace": {
            "name": marketplace_name,
            "manifest": ".agents/plugins/marketplace.json",
            "registration": "not-attempted",
        },
        "plugin": {
            "name": PLUGIN_NAME,
            "version": version,
            "path": f"plugins/{PLUGIN_NAME}",
            "installation": "not-verified",
            "expected_skill_count": 7,
        },
        "fixtures": fixture_paths,
        "communication_fixture": communication_fixture or {"runtime_loaded": False, "case_ids": []},
        "manual_project": "projects/manual-main",
        "safety": {
            "modifies_codex_configuration": False,
            "overwrites_existing_output": False,
            "removes_existing_files": False,
        },
    }
    write_json(output / "acceptance.json", record)
    write_text(output / "ACCEPTANCE.zh.md", manual_guide(marketplace_name, version))
    return record


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Prepare an isolated DeepScientist Lite Codex acceptance package.")
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--output", type=Path, required=True, help="Fresh output directory; existing paths are refused.")
    parser.add_argument("--cachebuster", default=f"local-{utc_stamp()}")
    parser.add_argument("--marketplace-name", help="Unique local marketplace name; defaults to the cachebuster.")
    parser.add_argument("--without-fixtures", action="store_true", help="Copy the plugin without generating teaching fixtures.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    marketplace_name = args.marketplace_name or f"ds-lite-acceptance-{args.cachebuster}"
    try:
        result = prepare(args.repo_root, args.output, args.cachebuster, marketplace_name, not args.without_fixtures)
    except (PreparationError, OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"Prepared acceptance package: {args.output.resolve()}")
    print("Next: add this directory as a marketplace source, then install the plugin from /plugins in a new Codex session.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
