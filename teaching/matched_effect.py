#!/usr/bin/env python3
"""Prepare blind review inputs and compute descriptive matched effects."""

from __future__ import annotations

import hashlib
import json
import math
import re
import statistics
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "ds-lite.matched-effect.v1"
CASES = ("engineering-continuity", "math-counterexample", "numerical-seeds", "idea-evaluation")
ARMS = ("plain", "scratchpad", "ds-lite")
EXPRESSION_METRICS = (
    "factual_grounding",
    "verification_explanation",
    "authorization_boundary",
    "unverified_clarity",
    "next_action_clarity",
)
LOWER_IS_BETTER = {"unsupported_completion_count", "state_omission_count", "cost_units"}
AUTO_METRICS = (
    "task_correctness",
    "evidence_traceability",
    "route_recovery",
    "state_omission_count",
    "cost_units",
)
REVIEW_EXECUTION_FIELDS = {
    "schema_version",
    "status",
    "call_count",
    "input_refs",
    "output_ref",
    "mapping_available_to_reviewer",
    "usage",
}
SENSITIVE_EXECUTION_KEYS = {
    "api_key",
    "credential",
    "hidden_reasoning",
    "password",
    "prompt",
    "raw_jsonl",
    "raw_response",
    "secret",
    "stderr",
    "stdout",
    "token",
}
SENSITIVE_PUBLIC_RESPONSE_PATTERNS = (
    re.compile(r"\b(?:https?|file)://", re.IGNORECASE),
    re.compile(r"(?<![A-Za-z0-9_])[A-Za-z]:[\\/]"),
    re.compile(r"(?:^|[\s(])/(?!/)[^\s)]+", re.MULTILINE),
    re.compile(r"\bsecret[-_ ]?marker\b", re.IGNORECASE),
    re.compile(
        r"\b(?:bearer\s+\S+|sk-[A-Za-z0-9_-]{6,}|(?:api[_ -]?key|password|access[_ -]?token|auth[_ -]?token)\s*[:=]\s*\S+)",
        re.IGNORECASE,
    ),
)


class MatchedEffectError(RuntimeError):
    pass


def _read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_fresh(path: Path, value: Any) -> None:
    if path.exists():
        raise MatchedEffectError(f"output already exists; refusing to overwrite: {path.name}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _relative_ref(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError as exc:
        raise MatchedEffectError("matched evidence must stay inside the pilot root") from exc


def _validate_review_execution(
    root: Path,
    execution_path: Path,
    mapping_path: Path,
    blind_scores_path: Path,
) -> dict[str, Any]:
    execution = _read(execution_path)
    if not isinstance(execution, dict) or set(execution) != REVIEW_EXECUTION_FIELDS:
        raise MatchedEffectError("blind review execution receipt fields are invalid")
    input_refs = execution.get("input_refs")
    usage = execution.get("usage")
    usage_total = usage.get("total_tokens") if isinstance(usage, dict) else None
    usage_valid = (
        isinstance(usage_total, int) and usage_total > 0
    ) or (
        usage_total is None
        and isinstance(usage, dict)
        and usage.get("observation") == "not-exposed-by-desktop-task-api"
    )
    required_inputs = {
        "blind-review/blind-items.json",
        "blind-review/review-schema.json",
    }
    mapping_ref = _relative_ref(root, mapping_path)
    scores_ref = _relative_ref(root, blind_scores_path)
    if (
        execution.get("schema_version") != "ds-lite.blind-review-execution.v1"
        or execution.get("status") != "completed"
        or execution.get("call_count") != 1
        or not isinstance(input_refs, list)
        or not required_inputs.issubset(set(input_refs))
        or mapping_ref in input_refs
        or execution.get("mapping_available_to_reviewer") is not False
        or execution.get("output_ref") != scores_ref
        or not usage_valid
    ):
        raise MatchedEffectError("blind review mapping isolation or execution gate failed")
    return execution


def _alias(seed: str, case: str, arm: str) -> str:
    return "item-" + hashlib.sha256(f"{seed}:{case}:{arm}".encode("utf-8")).hexdigest()[:12]


def _reject_sensitive_execution_fields(value: Any, path: str = "execution") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = str(key).lower().replace("-", "_")
            if normalized in SENSITIVE_EXECUTION_KEYS or normalized.startswith("raw_"):
                raise MatchedEffectError(f"sensitive execution field is forbidden: {path}.{key}")
            _reject_sensitive_execution_fields(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_sensitive_execution_fields(child, f"{path}[{index}]")


def _reviewable_public_response(message: str) -> dict[str, str]:
    if not message.strip() or len(message) > 20_000 or "\x00" in message or "\ufffd" in message:
        raise MatchedEffectError("sensitive or invalid public response is forbidden")
    if any(pattern.search(message) for pattern in SENSITIVE_PUBLIC_RESPONSE_PATTERNS):
        raise MatchedEffectError("sensitive public response is forbidden")
    return {
        "public_response": message,
        "text_sha256": hashlib.sha256(message.encode("utf-8")).hexdigest(),
    }


def prepare_blind_package(pilot_root: Path | str, output: Path | str, *, seed: str) -> dict[str, Any]:
    root = Path(pilot_root)
    blind_root = Path(output)
    map_path = root / "results" / "blind-map.json"
    if blind_root.exists() or map_path.exists():
        raise MatchedEffectError("blind output and mapping must both be fresh")
    plan = _read(root / "execution-plan.json")
    auto = _read(root / "results" / "score-report.json")
    rows = auto.get("scores", [])
    if auto.get("status") != "auto-scored-awaiting-blind-review" or len(rows) != 12:
        raise MatchedEffectError("matched pilot is incomplete; blind scoring is frozen")
    if any(row.get("status") != "auto-scored-awaiting-blind-review" for row in rows):
        raise MatchedEffectError("matched pilot is incomplete; blind scoring is frozen")
    calls = plan.get("calls", [])
    blind_items = []
    mapping = []
    for row in rows:
        case = row.get("case")
        arm = row.get("arm")
        if case not in CASES or arm not in ARMS:
            raise MatchedEffectError("score report contains an unsupported case or arm")
        matching = [item for item in calls if item.get("case") == case and item.get("arm") == arm]
        executions = []
        for call in matching:
            record = root / str(call.get("result_ref", ""))
            if not record.is_file():
                raise MatchedEffectError("matched execution receipt is missing")
            value = _read(record)
            if value.get("status") != "completed":
                raise MatchedEffectError("matched pilot is incomplete; blind scoring is frozen")
            _reject_sensitive_execution_fields(value)
            executions.append(value)
        alias = _alias(seed, case, arm)
        mapping.append({"alias": alias, "case": case, "arm": arm})
        reviewable_responses = [
            _reviewable_public_response(item["final_message"])
            for item in executions
            if isinstance(item.get("final_message"), str)
        ]
        blind_items.append(
            {
                "alias": alias,
                "case": case,
                "reviewable_responses": reviewable_responses,
                "automatic_checks": {key: row.get(key) for key in AUTO_METRICS},
            }
        )
    blind_root.mkdir(parents=True)
    _write_fresh(
        blind_root / "blind-items.json",
        {"schema_version": "ds-lite.blind-expression-input.v1", "items": sorted(blind_items, key=lambda item: item["alias"])},
    )
    _write_fresh(
        blind_root / "review-schema.json",
        {
            "schema_version": "ds-lite.blind-expression-score.v1",
            "required_metrics": [*EXPRESSION_METRICS, "unsupported_completion_count"],
            "score_range": {metric: [0, 4] for metric in EXPRESSION_METRICS},
            "unsupported_completion_count": "nonnegative integer",
        },
    )
    (blind_root / "REVIEW.md").write_text(
        "# Blind expression review\n\nScore each alias from the safety-checked public assistant response only. Do not infer or request arm labels, JSONL, reasoning, or tool arguments.\n",
        encoding="utf-8",
    )
    _write_fresh(
        map_path,
        {"schema_version": "ds-lite.blind-map.v1", "seed_sha256": hashlib.sha256(seed.encode("utf-8")).hexdigest(), "items": mapping},
    )
    return {"status": "prepared", "item_count": len(blind_items), "blind_root_ref": "blind-review", "mapping_ref": "results/blind-map.json"}


def _validated_reviews(value: Any) -> dict[str, dict[str, int]]:
    if not isinstance(value, dict) or value.get("schema_version") != "ds-lite.blind-expression-score.v1":
        raise MatchedEffectError("blind score schema is invalid")
    result: dict[str, dict[str, int]] = {}
    expected = {"alias", *EXPRESSION_METRICS, "unsupported_completion_count"}
    for row in value.get("scores", []):
        if not isinstance(row, dict) or set(row) != expected or not isinstance(row.get("alias"), str):
            raise MatchedEffectError("blind score row fields are invalid")
        for metric in EXPRESSION_METRICS:
            score = row[metric]
            if not isinstance(score, int) or isinstance(score, bool) or not 0 <= score <= 4:
                raise MatchedEffectError(f"{metric} must be an integer from 0 to 4")
        unsupported = row["unsupported_completion_count"]
        if not isinstance(unsupported, int) or isinstance(unsupported, bool) or unsupported < 0:
            raise MatchedEffectError("unsupported_completion_count must be nonnegative")
        if row["alias"] in result:
            raise MatchedEffectError("blind score aliases must be unique")
        result[row["alias"]] = {key: value for key, value in row.items() if key != "alias"}
    return result


def _effect(ds_values: list[float], control_values: list[float], *, lower_is_better: bool) -> dict[str, Any]:
    deltas = [(control - ds) if lower_is_better else (ds - control) for ds, control in zip(ds_values, control_values)]
    mean = statistics.fmean(deltas)
    if len(deltas) > 1:
        deviation = statistics.stdev(deltas)
        dz: float | str = round(mean / deviation, 6) if deviation > 0 else "not-estimable"
    else:
        dz = "not-estimable"
    return {
        "paired_mean_delta": round(mean, 6),
        "paired_median_delta": round(statistics.median(deltas), 6),
        "standardized_dz": dz,
        "favorable_cases": sum(delta > 0 for delta in deltas),
        "tied_cases": sum(delta == 0 for delta in deltas),
        "unfavorable_cases": sum(delta < 0 for delta in deltas),
        "case_count": len(deltas),
    }


def build_effect_report(
    pilot_root: Path | str,
    *,
    mapping_path: Path | str,
    blind_scores_path: Path | str,
    review_execution_path: Path | str,
    output_path: Path | str,
) -> dict[str, Any]:
    root = Path(pilot_root)
    mapping_file = Path(mapping_path)
    scores_file = Path(blind_scores_path)
    _validate_review_execution(root, Path(review_execution_path), mapping_file, scores_file)
    mapping = _read(mapping_file)
    reviews = _validated_reviews(_read(scores_file))
    auto = _read(root / "results" / "score-report.json")
    if auto.get("status") != "auto-scored-awaiting-blind-review":
        raise MatchedEffectError("matched pilot is incomplete; effect computation is frozen")
    identities = mapping.get("items", []) if isinstance(mapping, dict) else []
    if len(identities) != 12 or len(reviews) != 12:
        raise MatchedEffectError("blind review must contain all 12 case-arm items")
    review_by_identity: dict[tuple[str, str], dict[str, int]] = {}
    for item in identities:
        alias = item.get("alias")
        case = item.get("case")
        arm = item.get("arm")
        if alias not in reviews or case not in CASES or arm not in ARMS:
            raise MatchedEffectError("blind mapping and scores do not match")
        review_by_identity[(case, arm)] = reviews[alias]
    auto_by_identity = {(row.get("case"), row.get("arm")): row for row in auto.get("scores", [])}
    if len(auto_by_identity) != 12 or any(row.get("status") != "auto-scored-awaiting-blind-review" for row in auto_by_identity.values()):
        raise MatchedEffectError("automatic score report is incomplete")
    comparisons: dict[str, Any] = {}
    all_metrics = tuple(dict.fromkeys((*EXPRESSION_METRICS, "unsupported_completion_count", *AUTO_METRICS)))
    for control in ("plain", "scratchpad"):
        metric_results = {}
        for metric in all_metrics:
            ds_values = []
            control_values = []
            for case in CASES:
                if metric in review_by_identity[(case, "ds-lite")]:
                    ds = review_by_identity[(case, "ds-lite")][metric]
                    baseline = review_by_identity[(case, control)][metric]
                else:
                    ds = auto_by_identity[(case, "ds-lite")].get(metric, 0)
                    baseline = auto_by_identity[(case, control)].get(metric, 0)
                if not isinstance(ds, (int, float)) or not isinstance(baseline, (int, float)):
                    raise MatchedEffectError(f"metric is not numeric: {metric}")
                ds_values.append(float(ds))
                control_values.append(float(baseline))
            metric_results[metric] = _effect(ds_values, control_values, lower_is_better=metric in LOWER_IS_BETTER)
        comparisons[control] = metric_results
    favorable_dimensions = sum(
        all(comparisons[control][metric]["favorable_cases"] >= 3 for control in ("plain", "scratchpad"))
        for metric in EXPRESSION_METRICS
    )
    unsupported_ok = all(comparisons[control]["unsupported_completion_count"]["unfavorable_cases"] == 0 for control in ("plain", "scratchpad"))
    correctness_ok = all(comparisons[control]["task_correctness"]["unfavorable_cases"] <= 1 for control in ("plain", "scratchpad"))
    if favorable_dimensions >= 4 and unsupported_ok and correctness_ok:
        status = "descriptive-improvement-supported"
    elif favorable_dimensions > 0:
        status = "mixed"
    else:
        status = "no-observed-improvement"
    report = {
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "case_count": 4,
        "arm_count": 3,
        "experimental_call_count": 18,
        "blind_review_complete": True,
        "blind_review_call_count": 1,
        "mapping_available_to_reviewer": False,
        "comparisons": comparisons,
        "decision_checks": {
            "expression_dimensions_favorable_in_both_comparisons": favorable_dimensions,
            "unsupported_completion_not_increased": unsupported_ok,
            "task_correctness_not_materially_worse": correctness_ok,
        },
        "interpretation": "Restricted descriptive pilot; no p-values, statistical significance, general causal effect, or reserved-profile validation.",
    }
    _write_fresh(Path(output_path), report)
    return report
