#!/usr/bin/env python3
"""Score public artifacts from the redacted matched-control pilot."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterable


CASES = ("engineering-continuity", "math-counterexample", "numerical-seeds", "idea-evaluation")
ARMS = ("plain", "scratchpad", "ds-lite")
FIELDS = (
    "case",
    "arm",
    "status",
    "task_correctness",
    "recovery_time_seconds",
    "repeated_work_count",
    "state_omission_count",
    "negative_result_retained",
    "evidence_traceability",
    "route_recovery",
    "artifact_fragmentation",
    "speculation_leakage",
    "cost_units",
    "information_gain_per_cost",
    "notes",
)


class ScoreError(RuntimeError):
    pass


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _all_public_text(workspace: Path) -> str:
    parts = []
    for path in sorted(workspace.rglob("*")):
        if path.is_file() and path.suffix.lower() in {".md", ".txt", ".json", ".csv"}:
            parts.append(_read_text(path))
    return "\n".join(parts).lower()


def _json_objects(workspace: Path) -> Iterable[dict[str, Any]]:
    for path in sorted(workspace.rglob("*.json")):
        try:
            value = _read_json(path)
        except (OSError, ValueError):
            continue
        if isinstance(value, dict):
            yield value


def _cost(executions: list[dict[str, Any]]) -> int:
    total = 0
    for execution in executions:
        usage = execution.get("usage", {})
        value = usage.get("total_tokens", 0) if isinstance(usage, dict) else 0
        if isinstance(value, int) and value >= 0:
            total += value
    return total


def _speculation_leakage(text: str) -> int:
    count = 0
    for line in text.splitlines():
        lowered = line.lower()
        negated = any(term in lowered for term in ("not proof", "no proof", "not proven", "does not prove", "cannot prove", "不证明", "不能证明", "未证明"))
        if not negated and any(term in lowered for term in ("definitely novel", "proves that", "is proven", "statistically significant")):
            count += 1
    return count


def _fragmentation(workspace: Path, baseline_inventory: dict[str, str]) -> float:
    new_files = []
    reference_text = ""
    for path in sorted(item for item in workspace.rglob("*") if item.is_file()):
        if "__pycache__" in path.parts or path.suffix in {".pyc", ".pyo"}:
            continue
        relative = path.relative_to(workspace).as_posix()
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if baseline_inventory.get(relative) == digest:
            continue
        new_files.append(relative)
        if path.suffix.lower() in {".md", ".txt", ".json"}:
            reference_text += "\n" + _read_text(path)
    if not new_files:
        return 0.0
    required_names = {
        "ROUND_1_REPORT.md",
        "ROUND_2_REPORT.md",
        "FINAL_REPORT.md",
        "REPORT.md",
        "IDEA_DECISION.md",
        "early.json",
        "expanded.json",
        "early-wsl-proof.json",
        "wsl-proof.json",
    }
    unreferenced = [
        relative
        for relative in new_files
        if Path(relative).name not in required_names and Path(relative).name not in reference_text
    ]
    return round(len(unreferenced) / len(new_files), 4)


def _engineering_score(workspace: Path) -> tuple[int, int, int, int]:
    materials = workspace / "materials"
    suite = subprocess.run(
        [sys.executable, "-m", "unittest", "-v"],
        cwd=materials,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    ) if materials.is_dir() else None
    checks = [bool(suite and suite.returncode == 0)]
    probe = """
import json
from slugger import make_slug
result = {}
result['accent'] = make_slug('Caf\u00e9 \u00c9tude') == 'cafe-etude'
try:
    make_slug('!!!')
except ValueError:
    result['empty'] = True
else:
    result['empty'] = False
result['reserved'] = make_slug('admin') == 'admin-item' and make_slug('api') == 'api-item'
print(json.dumps(result))
"""
    hidden: dict[str, Any] = {}
    if materials.is_dir():
        completed = subprocess.run(
            [sys.executable, "-c", probe],
            cwd=materials,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )
        if completed.returncode == 0:
            try:
                hidden = json.loads(completed.stdout)
            except ValueError:
                hidden = {}
    checks.extend(bool(hidden.get(name)) for name in ("accent", "empty", "reserved"))
    reports = [workspace / name for name in ("ROUND_1_REPORT.md", "ROUND_2_REPORT.md", "FINAL_REPORT.md")]
    omissions = 0
    for report in reports:
        text = _read_text(report).lower()
        if not report.is_file() or not all(term in text for term in ("contract", "next action")):
            omissions += 1
    final = _read_text(workspace / "FINAL_REPORT.md").lower()
    route = 4 if all(term in final for term in ("contract", "next action")) else (2 if final else 0)
    traceability = min(4, int(checks[0]) + sum(report.is_file() for report in reports))
    return sum(checks), omissions, traceability, route


def _math_score(workspace: Path, text: str) -> tuple[int, int, int, int]:
    exact = False
    for value in _json_objects(workspace):
        counterexample = value.get("first_counterexample")
        if isinstance(counterexample, dict) and counterexample == {"n": 40, "value": 1681, "smallest_divisor": 41}:
            exact = True
            break
    report = _read_text(workspace / "REPORT.md").lower()
    facts = [
        exact,
        all(term in report for term in ("40", "1681", "41")),
        any(term in report for term in ("refuted", "counterexample", "反例", "不成立")),
        any(term in report for term in ("not a proof", "not proof", "不能证明", "不是证明")),
    ]
    traceability = 4 if exact and report else (2 if exact or report else 0)
    route = 4 if exact and facts[2] else (2 if report else 0)
    return sum(facts), int(exact and facts[2]), traceability, route


def _numerical_score(workspace: Path, text: str) -> tuple[int, int, int, int]:
    early = None
    expanded = None
    try:
        early = _read_json(workspace / "early.json")
        expanded = _read_json(workspace / "expanded.json")
    except (OSError, ValueError):
        pass
    seeds_ok = (
        isinstance(early, dict)
        and early.get("seed_count") == 2
        and isinstance(early.get("rows"), list)
        and len(early["rows"]) == 2
        and isinstance(expanded, dict)
        and expanded.get("seed_count") == 20
        and isinstance(expanded.get("rows"), list)
        and len(expanded["rows"]) == 20
    )
    reversal = False
    if isinstance(early, dict) and isinstance(expanded, dict):
        early_diff = early.get("mean_a", 0) - early.get("mean_b", 0)
        expanded_diff = expanded.get("mean_a", 0) - expanded.get("mean_b", 0)
        reversal = early_diff * expanded_diff < 0
    proofs_ok = True
    for name, count in (("early-wsl-proof.json", 2), ("wsl-proof.json", 20)):
        try:
            proof = _read_json(workspace / name)
        except (OSError, ValueError):
            proofs_ok = False
            continue
        proofs_ok = proofs_ok and all(
            (
                proof.get("schema_version") == "ds-lite.wsl-computation-proof.v1",
                proof.get("distribution") == "DS-Lite-Ubuntu-24.04",
                proof.get("kernel") == "Linux",
                proof.get("seed_count") == count,
            )
        )
    report = _read_text(workspace / "REPORT.md").lower()
    cautious = any(term in report for term in ("inconclusive", "uncertain", "不确定", "证据不足")) and any(
        term in report for term in ("no significance", "not significant", "不作显著性", "不能宣称显著")
    )
    facts = [seeds_ok, reversal, proofs_ok, cautious]
    traceability = 4 if seeds_ok and proofs_ok and report else (2 if seeds_ok or proofs_ok else 0)
    route = 4 if reversal and cautious else (2 if report else 0)
    return sum(facts), int(reversal and bool(early) and bool(expanded)), traceability, route


def _idea_score(workspace: Path, text: str) -> tuple[int, int, int, int]:
    report = _read_text(workspace / "IDEA_DECISION.md").lower()
    dimensions = ("novelty", "feasibility", "evidence strength", "cost", "risk", "alignment")
    candidates = all(candidate in report for candidate in ("idea-a", "idea-b", "idea-c"))
    six_dimensions = all(dimension in report for dimension in dimensions)
    unknown_novelty = "novelty" in report and any(term in report for term in ("unknown", "未知", "not established"))
    bounded_decision = any(term in report for term in ("smallest validation experiment", "minimum experiment", "最小验证实验")) and any(
        term in report for term in ("no automatic total", "not use an automatic total", "不自动求和", "禁止自动总分")
    )
    sources = 4 if "s1-s4" in report else sum(f"s{index}" in report for index in range(1, 5))
    traceability = min(4, sources)
    route = 4 if bounded_decision else (2 if report else 0)
    return sum((candidates, six_dimensions, unknown_novelty, bounded_decision)), -1, traceability, route


def score_arm(
    case: str,
    arm: str,
    workspace: Path | str,
    executions: list[dict[str, Any]],
    *,
    baseline_inventory: dict[str, str],
) -> dict[str, Any]:
    if case not in CASES or arm not in ARMS:
        raise ScoreError(f"unsupported case/arm: {case}/{arm}")
    root = Path(workspace)
    text = _all_public_text(root)
    if case == "engineering-continuity":
        correctness, omissions, traceability, route = _engineering_score(root)
        negative: int | str = "not-applicable"
    elif case == "math-counterexample":
        correctness, negative, traceability, route = _math_score(root, text)
        omissions = int(not (root / "REPORT.md").is_file())
    elif case == "numerical-seeds":
        correctness, negative, traceability, route = _numerical_score(root, text)
        omissions = int(not (root / "REPORT.md").is_file())
    else:
        correctness, negative, traceability, route = _idea_score(root, text)
        omissions = int(not (root / "IDEA_DECISION.md").is_file())
    cost_units = _cost(executions)
    recovery = 0.0
    if case == "engineering-continuity":
        recovery = next(
            (float(item.get("elapsed_seconds", 0)) for item in executions if item.get("round") == 3),
            0.0,
        )
    completed = bool(executions) and all(item.get("status") == "completed" for item in executions)
    information = correctness + traceability + route + (negative if isinstance(negative, int) and negative > 0 else 0)
    return {
        "case": case,
        "arm": arm,
        "status": "auto-scored-awaiting-blind-review" if completed else "incomplete",
        "task_correctness": correctness,
        "recovery_time_seconds": recovery,
        "repeated_work_count": 0,
        "state_omission_count": omissions,
        "negative_result_retained": negative,
        "evidence_traceability": traceability,
        "route_recovery": route,
        "artifact_fragmentation": _fragmentation(root, baseline_inventory),
        "speculation_leakage": _speculation_leakage(text),
        "cost_units": cost_units,
        "information_gain_per_cost": round(information / cost_units, 6) if cost_units else "",
        "notes": "Automatic artifact checks only; blind human rubric review is still required.",
    }


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def score_pilot(windows_root: Path | str, wsl_root: Path | str) -> dict[str, Any]:
    windows = Path(windows_root)
    wsl = Path(wsl_root)
    try:
        plan_payload = _read_json(windows / "execution-plan.json")
        baselines = _read_json(windows / "results" / "baseline-files.json")
    except (OSError, ValueError) as exc:
        raise ScoreError(f"pilot inputs are incomplete: {exc}") from exc
    execution_by_call: dict[str, dict[str, Any]] = {}
    for item in plan_payload.get("calls", []):
        record = windows / item["result_ref"]
        if record.is_file():
            execution_by_call[item["call_id"]] = _read_json(record)
    scores = []
    for case in CASES:
        for arm in ARMS:
            items = [item for item in plan_payload["calls"] if item["case"] == case and item["arm"] == arm]
            executions = [execution_by_call[item["call_id"]] for item in items if item["call_id"] in execution_by_call]
            surface = wsl if case == "numerical-seeds" else windows
            scores.append(
                score_arm(
                    case,
                    arm,
                    surface / f"arms/{case}/{arm}",
                    executions,
                    baseline_inventory=baselines.get(f"{case}--{arm}", {}),
                )
            )
    status = "auto-scored-awaiting-blind-review" if all(row["status"] == "auto-scored-awaiting-blind-review" for row in scores) else "incomplete"
    results = windows / "results"
    results.mkdir(parents=True, exist_ok=True)
    with (results / "scores.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(scores)
    report = {
        "schema_version": "ds-lite.matched-pilot-score-report.v1",
        "pilot_id": plan_payload.get("pilot_id", "unknown"),
        "status": status,
        "arm_count": len(scores),
        "scores": scores,
        "interpretation": "Descriptive pilot only; no statistical significance or reserved-profile validation claim.",
        "extensions": {},
    }
    _write_json(results / "score-report.json", report)
    table = [
        "# Matched pilot 自动评分摘要",
        "",
        f"状态：`{status}`。自动检查只覆盖公开产物，仍需隐藏 arm 标签后的人工复核。",
        "",
        "| 案例 | arm | 正确率 | 证据追溯 | 路线恢复 | token |",
        "| --- | --- | ---: | ---: | ---: | ---: |",
    ]
    table.extend(
        f"| {row['case']} | {row['arm']} | {row['task_correctness']} | {row['evidence_traceability']} | {row['route_recovery']} | {row['cost_units']} |"
        for row in scores
    )
    table.extend(
        [
            "",
            "本轮仅作描述性比较，不宣称统计显著性；单次 pilot 不验证 literature、mathematical、software 或 numerical 保留 profile。",
        ]
    )
    (results / "analysis.zh.md").write_text("\n".join(table) + "\n", encoding="utf-8")
    return report


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Score redacted public artifacts from the DeepScientist Lite matched pilot.")
    subcommands = result.add_subparsers(dest="command", required=True)
    score = subcommands.add_parser("score", help="score all 12 case-arm workspaces")
    score.add_argument("--windows-root", type=Path)
    score.add_argument("--wsl-root", type=Path)
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        windows_root = args.windows_root or (Path(os.environ["DS_LITE_PILOT_WINDOWS_ROOT"]) if os.environ.get("DS_LITE_PILOT_WINDOWS_ROOT") else None)
        wsl_root = args.wsl_root or (Path(os.environ["DS_LITE_PILOT_WSL_ROOT"]) if os.environ.get("DS_LITE_PILOT_WSL_ROOT") else None)
        if windows_root is None or wsl_root is None:
            raise ScoreError("pass --windows-root and --wsl-root, or set DS_LITE_PILOT_WINDOWS_ROOT and DS_LITE_PILOT_WSL_ROOT")
        report = score_pilot(windows_root, wsl_root)
    except (ScoreError, OSError, ValueError, KeyError) as exc:
        print(f"pilot scoring failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({"pilot_id": report["pilot_id"], "status": report["status"], "arm_count": report["arm_count"]}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
