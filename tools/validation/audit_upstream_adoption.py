#!/usr/bin/env python3
"""Build and validate the fixed upstream communication adoption inventory."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
PLUGIN_ROOT = REPO_ROOT / "plugins" / "deepscientist-lite"
COMMUNICATION_ROOT = PLUGIN_ROOT / "references" / "communication"
SOURCE_MANIFEST = COMMUNICATION_ROOT / "upstream" / "_manifests" / "source-files.json"
ADOPTION_MATRIX = COMMUNICATION_ROOT / "upstream-adoption.json"
AUDIT_DOC = REPO_ROOT / "docs" / "maintainers" / "upstream-adoption-audit.zh.md"
DECISIONS = {
    "adopted",
    "adapted",
    "rejected",
    "metadata-only",
    "license-only",
    "asset-only",
}


def local_reference(name: str) -> str:
    return f"plugins/deepscientist-lite/references/communication/{name}"


def classification(entry: dict[str, Any]) -> dict[str, Any]:
    repository = entry["repository"]
    source_path = entry["source_path"]
    decision = "metadata-only"
    local_refs = ["docs/maintainers/upstream-adoption-audit.zh.md"]
    rule_ids = ["UPSTREAM-INVENTORY"]
    reason = (
        "Repository metadata or maintenance material is preserved for provenance "
        "and audited, but it is not loaded at runtime."
    )
    test_refs = ["tests/test_upstream_adoption.py"]

    if source_path == "LICENSE":
        decision = "license-only"
        local_refs = ["plugins/deepscientist-lite/THIRD_PARTY_NOTICES.md", "NOTICE"]
        rule_ids = ["LICENSE-EXACT"]
        reason = "The exact upstream license is preserved and verified byte-for-byte."
    elif repository == "ai-zixun/humanizer-zh" and source_path == "SKILL.md":
        decision = "adapted"
        local_refs = [local_reference("humanizer-zh.md"), local_reference("self-audit.md")]
        rule_ids = ["ZH-WORKFLOW", "ZH-FINAL-CHECK", "ZH-PRESERVE"]
        reason = (
            "Adapts text-type selection, rewrite depth, article coherence, preservation, "
            "and final read-aloud checks without importing the upstream skill workflow wholesale."
        )
    elif repository == "ai-zixun/humanizer-zh" and source_path == "references/patterns.md":
        decision = "adapted"
        local_refs = [local_reference("humanizer-zh.md")]
        rule_ids = ["ZH-PATTERN-01-13"]
        reason = (
            "Adapts all thirteen diagnostic categories into research-facing Chinese guidance "
            "with evidence and protected-content boundaries."
        )
    elif repository == "ai-zixun/humanizer-zh" and source_path in {
        "references/corpus.md",
        "references/corpus-quickpick.md",
    }:
        decision = "adapted"
        local_refs = [local_reference("humanizer-zh.md"), local_reference("profiles.md")]
        rule_ids = ["ZH-TEXT-TYPE", "ZH-REFERENCE-WITHOUT-IMITATION"]
        reason = (
            "Adapts genre selection and rhythm observations while removing named-author "
            "imitation and persona adoption."
        )
    elif repository == "ai-zixun/humanizer-zh" and (
        source_path == "references/voices/index.md"
        or source_path.startswith("references/voices/")
    ):
        decision = "rejected"
        local_refs = [local_reference("profiles.md"), local_reference("core.md")]
        rule_ids = ["REJECT-NAMED-AUTHOR-IMITATION"]
        reason = (
            "The file is fully audited but excluded from runtime because named-author persona "
            "imitation conflicts with the plugin boundary; only generic structural observations "
            "may be restated in original rules."
        )
    elif repository == "ai-zixun/humanizer-zh" and source_path == "CLAUDE.md":
        decision = "adapted"
        local_refs = [local_reference("core.md"), "plugins/deepscientist-lite/assets/templates/STYLE.md"]
        rule_ids = ["STYLE-PRECEDENCE", "QUOTE-PREFERENCE"]
        reason = (
            "Adapts project-rule precedence and configurable quote preferences without "
            "importing Claude-specific instructions."
        )
    elif repository == "blader/humanizer" and source_path == "SKILL.md":
        decision = "adapted"
        local_refs = [local_reference("humanizer-en.md"), local_reference("self-audit.md")]
        rule_ids = ["EN-PATTERN-01-33", "EN-DRAFT-AUDIT-FINAL", "EN-FALSE-POSITIVE-GUARD"]
        reason = (
            "Adapts the complete 33-pattern taxonomy, preservation safeguards, and "
            "draft-audit-final workflow for research communication."
        )
    elif repository == "blader/humanizer" and source_path == "README.md":
        decision = "adapted"
        local_refs = [local_reference("humanizer-en.md"), "docs/maintainers/upstream-adoption-audit.zh.md"]
        rule_ids = ["EN-PATTERN-INDEX", "EN-VOICE-CALIBRATION"]
        reason = "Uses the documented pattern index and final audit rationale as a maintenance cross-check."
    elif repository == "blader/humanizer" and source_path == "AGENTS.md":
        decision = "adapted"
        local_refs = [local_reference("self-audit.md"), "tools/validation/validate_repo.py"]
        rule_ids = ["SOURCE-GENERATED-SYNC"]
        reason = (
            "Adapts the source-of-truth and synchronized-document maintenance discipline "
            "into deterministic repository validation."
        )
    elif repository == "AIScientists-Dev/academic-humanizer" and source_path == "SKILL.md":
        decision = "adapted"
        local_refs = [local_reference("academic-writing.md"), local_reference("self-audit.md")]
        rule_ids = [
            "ACADEMIC-LAYER-01-06",
            "CLAIM-EVIDENCE",
            "CLAIM-FEASIBILITY",
            "ACADEMIC-REPORT",
        ]
        reason = (
            "Adapts all six academic layers, audit-rewrite-report, evidence-matched claims, "
            "scholarly preservation, venue voice, and proposal feasibility."
        )
    elif repository == "AIScientists-Dev/academic-humanizer" and source_path == "README.md":
        decision = "adapted"
        local_refs = [local_reference("academic-writing.md"), "docs/maintainers/upstream-adoption-audit.zh.md"]
        rule_ids = ["ACADEMIC-ETHICS", "ACADEMIC-PERSONALIZATION"]
        reason = "Adapts the ethics, disclosure, personalization, and non-evasion boundaries."
    elif (
        repository == "AIScientists-Dev/academic-humanizer"
        and source_path == "examples/before-after.md"
    ):
        decision = "adapted"
        local_refs = [local_reference("academic-writing.md"), "tools/validation/prepare_codex_acceptance.py"]
        rule_ids = ["ACADEMIC-EXAMPLE-COVERAGE", "PROPOSAL-MODE"]
        reason = (
            "Uses the examples to derive original fixed regression prompts for paper and "
            "proposal registers; example text is not copied into runtime output."
        )
    elif repository == "AIScientists-Dev/academic-humanizer" and source_path.startswith("assets/"):
        decision = "asset-only"
        local_refs = ["docs/maintainers/upstream-adoption-audit.zh.md"]
        rule_ids = ["ASSET-INVENTORY"]
        reason = (
            "Binary or visual assets are preserved and hashed for completeness but are not "
            "interpreted as writing rules or loaded at runtime."
        )

    return {
        "repository": entry["repository"],
        "commit": entry["commit"],
        "source_path": entry["source_path"],
        "source_sha256": entry["source_sha256"],
        "decision": decision,
        "local_refs": local_refs,
        "rule_ids": rule_ids,
        "reason": reason,
        "test_refs": test_refs,
    }


def local_artifacts() -> list[dict[str, Any]]:
    rows = (
        (local_reference("core.md"), "mixed", ["STYLE-PRECEDENCE", "EIGHT-HONORS", "CLAIM-SUPPORT"]),
        (local_reference("profiles.md"), "mixed", ["PROFILE-FOUR", "REJECT-NAMED-AUTHOR-IMITATION"]),
        (local_reference("self-audit.md"), "mixed", ["START-ACTION-HANDOFF", "SOURCE-GENERATED-SYNC"]),
        (local_reference("humanizer-zh.md"), "adapted", ["ZH-WORKFLOW", "ZH-PATTERN-01-13"]),
        (local_reference("humanizer-en.md"), "adapted", ["EN-PATTERN-01-33", "EN-DRAFT-AUDIT-FINAL"]),
        (local_reference("academic-writing.md"), "adapted", ["ACADEMIC-LAYER-01-06", "CLAIM-EVIDENCE", "CLAIM-FEASIBILITY"]),
        (local_reference("upstream-adoption.json"), "generated", ["UPSTREAM-INVENTORY", "NINE-FIELD-MATRIX"]),
        (local_reference("upstream/_manifests/source-files.json"), "generated", ["SOURCE-SNAPSHOT-HASH"]),
        ("plugins/deepscientist-lite/assets/templates/STYLE.md", "project-native", ["PROFILE-CONFIG"]),
        ("plugins/deepscientist-lite/scripts/ds_lite_communication_audit.py", "project-native", ["COMMUNICATION-AUDIT-V1"]),
        ("plugins/deepscientist-lite/scripts/ds_lite_hook.py", "project-native", ["HOOK-FOUR-EVENTS", "CLAIM-GATE"]),
        ("plugins/deepscientist-lite/hooks/hooks.json", "project-native", ["HOOK-ADAPTER"]),
        ("plugins/deepscientist-lite/THIRD_PARTY_NOTICES.md", "generated", ["LICENSE-EXACT"]),
        ("tests/test_communication_layer.py", "project-native", ["COMMUNICATION-REFERENCE-TEST"]),
        ("tests/test_communication_audit.py", "project-native", ["COMMUNICATION-AUDIT-TEST"]),
        ("tests/test_communication_hook.py", "project-native", ["HOOK-BEHAVIOR-TEST"]),
        ("tests/test_upstream_adoption.py", "project-native", ["UPSTREAM-AUDIT-TEST"]),
        ("docs/maintainers/upstream-adoption-audit.zh.md", "generated", ["UPSTREAM-INVENTORY"]),
    )
    return [
        {
            "path": path,
            "origin": origin,
            "rule_ids": rule_ids,
            "reason": (
                "Original DeepScientist Lite contract or deterministic enforcement code."
                if origin == "project-native"
                else "Generated or adapted from the explicitly mapped fixed upstream sources."
            ),
        }
        for path, origin, rule_ids in rows
    ]


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def build_matrix() -> dict[str, Any]:
    manifest = load_json(SOURCE_MANIFEST)
    entries = manifest.get("entries")
    if not isinstance(entries, list):
        raise ValueError("source manifest entries must be an array")
    return {
        "schema_version": "ds-lite.upstream-adoption.v1",
        "runtime_loaded": False,
        "source_manifest": SOURCE_MANIFEST.relative_to(REPO_ROOT).as_posix(),
        "decision_values": sorted(DECISIONS),
        "entries": [classification(entry) for entry in entries],
        "local_artifacts": local_artifacts(),
    }


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def chinese_reason(entry: dict[str, Any]) -> str:
    rule_ids = set(entry["rule_ids"])
    if "LICENSE-EXACT" in rule_ids:
        return "逐字保留许可证和版权声明，并用文件哈希验证；不把许可证改写成通用模板。"
    if "REJECT-NAMED-AUTHOR-IMITATION" in rule_ids:
        return "已审读并保留快照，但拒绝具名作者人格、口癖和仿写指令；只化用可泛化的结构观察。"
    if "ASSET-INVENTORY" in rule_ids:
        return "仅作资产完整性和哈希审计，不从图片或 SVG 推导写作规则，也不加载到运行时。"
    if "ZH-WORKFLOW" in rule_ids:
        return "化用文本类型、改写力度、全文主线、保真和朗读复查，重写为科研沟通规则。"
    if "ZH-PATTERN-01-13" in rule_ids:
        return "十三类中文模式全部进入本地规则索引，并增加证据、术语和结构化内容保护。"
    if "ZH-TEXT-TYPE" in rule_ids:
        return "化用按文体选择节奏和结构的办法；删除作者名单和模仿入口。"
    if "STYLE-PRECEDENCE" in rule_ids:
        return "化用项目规则优先级和引号偏好；不复制 Claude 专用配置。"
    if "EN-PATTERN-01-33" in rule_ids:
        return "完整映射 33 类英文模式、误报保护和 draft-audit-final 流程。"
    if "EN-PATTERN-INDEX" in rule_ids:
        return "用于核对模式数量、名称和维护同步，不把 README 当运行时入口。"
    if "SOURCE-GENERATED-SYNC" in rule_ids:
        return "化用源文件与用户文档同步的维护纪律，并交给确定性验证器检查。"
    if "ACADEMIC-LAYER-01-06" in rule_ids:
        return "完整化用六层学术规则、claim-evidence、proposal feasibility 和变更报告。"
    if "ACADEMIC-ETHICS" in rule_ids:
        return "化用学术伦理、披露、个性化和非检测规避边界。"
    if "ACADEMIC-EXAMPLE-COVERAGE" in rule_ids:
        return "用于设计原创固定回归案例；示例原文不进入运行时输出。"
    return "仅用于来源、版本、构建或分发审计；不转化为运行时表达规则。"


def source_role(entry: dict[str, Any]) -> str:
    path = entry["source_path"]
    if path == "LICENSE":
        return "许可证"
    if path == "SKILL.md":
        return "运行时规则入口"
    if path.startswith("references/voices/"):
        return "具名作者声音档案"
    if path.startswith("references/"):
        return "深度写作参考"
    if path.startswith("examples/"):
        return "示例与回归依据"
    if path.startswith("assets/"):
        return "视觉资产"
    if path.startswith("README") or path == "CHANGELOG.md":
        return "用户或版本文档"
    return "仓库元数据或维护配置"


def render_audit_doc(matrix: dict[str, Any]) -> str:
    decision_zh = {
        "adapted": "化用",
        "adopted": "采纳",
        "rejected": "拒绝运行时采用",
        "metadata-only": "仅元数据",
        "license-only": "仅许可证",
        "asset-only": "仅资产",
    }
    lines = [
        "# 沟通层上游逐文件采用审计",
        "",
        "> 状态：`0.5.0-beta.2` 源码审计资料；`runtime_loaded: false`。",
        "",
        "本文逐文件记录三个固定提交的用途、哈希、采用结论、本地落点和拒绝边界。",
        "完整快照用于离线复核，不由七个科研 skill 直接加载。目录项没有被省略；",
        "二进制资产只验证字节和哈希，具名作者档案只审读、不运行。",
        "",
        "## 判定规则",
        "",
        "- `化用`：保留方法和可检验规则，用 DeepScientist Lite 的原创表达重新组织。",
        "- `拒绝运行时采用`：文件仍完整保存和审读，但其人格模仿或其他内容不进入运行时。",
        "- `仅元数据/许可证/资产`：只服务来源、法律或完整性审计。",
        "- 每一行必须与 `upstream-adoption.json` 一致；验证器发现遗漏、重复或哈希漂移即失败。",
        "",
    ]
    repositories = sorted({entry["repository"] for entry in matrix["entries"]})
    for repository in repositories:
        entries = [entry for entry in matrix["entries"] if entry["repository"] == repository]
        commit = entries[0]["commit"]
        lines.extend(
            [
                f"## `{repository}@{commit}`",
                "",
                "| 源文件 | 用途 | SHA-256 | 结论 | 本地落点 | 逐文件说明 |",
                "| --- | --- | --- | --- | --- | --- |",
            ]
        )
        for entry in sorted(entries, key=lambda item: item["source_path"]):
            refs = "<br>".join(f"`{ref}`" for ref in entry["local_refs"])
            reason = chinese_reason(entry).replace("|", "\\|")
            lines.append(
                f"| `{entry['source_path']}` | {source_role(entry)} | "
                f"`{entry['source_sha256'][:16]}...` | {decision_zh[entry['decision']]} | "
                f"{refs} | {reason} |"
            )
        lines.append("")

    lines.extend(
        [
            "## 本地生成文件反向映射",
            "",
            "| 本地文件 | 来源类型 | 规则编号 | 说明 |",
            "| --- | --- | --- | --- |",
        ]
    )
    for item in matrix["local_artifacts"]:
        rules = ", ".join(f"`{rule}`" for rule in item["rule_ids"])
        lines.append(f"| `{item['path']}` | `{item['origin']}` | {rules} | {item['reason']} |")
    lines.extend(
        [
            "",
            "## 明确不采用",
            "",
            "- 不启用任何具名作者 persona，不复制作者口癖，不提供作者模仿 profile。",
            "- 不把上游 skill、Claude 插件清单、marketplace 或发布流程变成 DS Lite 运行时依赖。",
            "- 不把视觉资产解释成文本规则，不从示例补造科研数据、引用、合作方或实验结果。",
            "- 不使用 humanizer 掩盖 AI 辅助披露义务，也不把表达改写当成证据验证。",
            "",
            "## 复核命令",
            "",
            "```bash",
            "python tools/validation/audit_upstream_adoption.py",
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def validate() -> list[str]:
    errors: list[str] = []
    expected = build_matrix()
    actual = load_json(ADOPTION_MATRIX)
    if actual != expected:
        errors.append("upstream adoption matrix differs from the deterministic classification")

    source_manifest = load_json(SOURCE_MANIFEST)
    source_entries = {
        (entry["repository"], entry["commit"], entry["source_path"]): entry
        for entry in source_manifest.get("entries", [])
    }
    seen: set[tuple[str, str, str]] = set()
    for entry in expected["entries"]:
        key = (entry["repository"], entry["commit"], entry["source_path"])
        if key in seen:
            errors.append(f"duplicate upstream file entry: {key}")
        seen.add(key)
        source = source_entries.get(key)
        if source is None:
            errors.append(f"upstream file is absent from source manifest: {key}")
            continue
        snapshot = REPO_ROOT / str(source["local_snapshot"]).replace("\\", "/")
        if not snapshot.is_file():
            errors.append(f"missing upstream snapshot: {source['local_snapshot']}")
            continue
        if snapshot.stat().st_size != source["size"]:
            errors.append(f"upstream size mismatch: {source['local_snapshot']}")
        if sha256(snapshot) != entry["source_sha256"]:
            errors.append(f"upstream SHA-256 mismatch: {source['local_snapshot']}")
        if entry["decision"] not in DECISIONS:
            errors.append(f"unsupported adoption decision: {entry['decision']}")
        for field in ("local_refs", "rule_ids", "reason", "test_refs"):
            if not entry.get(field):
                errors.append(f"empty {field} for upstream file: {key}")

    for item in expected["local_artifacts"]:
        if not (REPO_ROOT / item["path"]).exists():
            errors.append(f"missing mapped local artifact: {item['path']}")

    for skill_file in (PLUGIN_ROOT / "skills").glob("*/SKILL.md"):
        if "references/communication/upstream/" in skill_file.read_text(encoding="utf-8"):
            errors.append(f"runtime skill directly loads upstream snapshot: {skill_file}")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="Write the deterministic adoption matrix.")
    parser.add_argument("--write-doc", action="store_true", help="Write the human-readable audit table.")
    args = parser.parse_args(argv)
    try:
        if args.write:
            ADOPTION_MATRIX.write_text(
                json.dumps(build_matrix(), ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            print(f"Wrote {ADOPTION_MATRIX.relative_to(REPO_ROOT).as_posix()}")
            return 0
        if args.write_doc:
            matrix = load_json(ADOPTION_MATRIX)
            AUDIT_DOC.write_text(render_audit_doc(matrix), encoding="utf-8")
            print(f"Wrote {AUDIT_DOC.relative_to(REPO_ROOT).as_posix()}")
            return 0
        errors = validate()
    except (OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print("OK: upstream adoption inventory is complete and reproducible.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
