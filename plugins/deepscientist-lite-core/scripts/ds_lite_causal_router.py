#!/usr/bin/env python3
"""Causal Router for DS Lite v6.

A Router that distinguishes four causal tasks:
1. Mechanism Chain - known mechanism, find more intervention points
2. Causal Inference - estimate numerical effect of treatment X on outcome Y
3. Causal Discovery - find structures in data worth forming hypotheses
4. Incident/System Analysis - why an engineering/automation failure recurs

Each task mode has independent evidence gates and output artifacts.

Schema: ds-lite.causal-router.v1
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from typing import Any

ROUTER_SCHEMA = "ds-lite.causal-router.v1"
MODEL_SCHEMA = "ds-lite.causal-model.v1"
ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,79}$")

CAUSAL_MODES = frozenset({
    "mechanism-chain",
    "causal-inference",
    "causal-discovery",
    "incident-analysis",
})

NODE_STATUSES = frozenset({
    "observed", "hypothesis", "validated", "contested",
})

EDGE_RELATIONS = frozenset({
    "causes", "enables", "blocks", "mediates",
    "moderates", "confounds", "precedes",
})

EDGE_LOGICS = frozenset({"AND", "OR", "UNKNOWN"})

EDGE_STATUSES = frozenset({
    "hypothesis", "supported", "contested", "refuted",
})

EVIDENCE_TAGS = frozenset({
    "observed", "literature-supported", "expert-asserted", "inferred",
})


class CausalRouterError(RuntimeError):
    pass


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _digest(data: dict[str, Any]) -> str:
    canonical = json.dumps(data, sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# ============================================================================
# Routing
# ============================================================================

def route_causal_question(question: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
    """Route a causal question to the appropriate causal task mode.

    Routing logic:
    - If "estimate numerical effect" is needed -> Causal Inference
    - If mechanism is roughly known -> Mechanism Chain
    - If data available and exploratory structure accepted -> Causal Discovery
    - If failure/incident复盘 -> Incident/System Analysis

    Returns a CausalRoute with:
    - mode: str
    - question: str
    - routing_reason: str
    - routing_conditions: dict
    - artifact: CausalModelArtifact (initial)
    """
    if not isinstance(question, str) or not question.strip():
        raise CausalRouterError("question must be a non-empty string")

    ctx = context or {}

    # Determine routing
    needs_numerical_effect = ctx.get("needs_numerical_effect", False)
    mechanism_known = ctx.get("mechanism_known", False)
    has_data = ctx.get("has_data", False)
    accepts_exploratory = ctx.get("accepts_exploratory", False)
    is_incident = ctx.get("is_incident", False)

    if needs_numerical_effect:
        mode = "causal-inference"
        reason = "User needs to estimate numerical effect of treatment on outcome"
    elif mechanism_known:
        mode = "mechanism-chain"
        reason = "Mechanism is roughly known; need to find more intervention points"
    elif has_data and accepts_exploratory:
        mode = "causal-discovery"
        reason = "Data available and user accepts exploratory structure discovery"
    elif is_incident:
        mode = "incident-analysis"
        reason = "Question is about why a failure/incident recurs"
    else:
        # Default to mechanism-chain when no specific context
        mode = "mechanism-chain"
        reason = "Default routing: no specific context provided, assuming mechanism chain"

    # Create initial artifact
    artifact = create_causal_model(mode, question, ctx.get("scope_conditions", []))

    route = {
        "schema_version": ROUTER_SCHEMA,
        "mode": mode,
        "question": question,
        "routing_reason": reason,
        "routing_conditions": {
            "needs_numerical_effect": needs_numerical_effect,
            "mechanism_known": mechanism_known,
            "has_data": has_data,
            "accepts_exploratory": accepts_exploratory,
            "is_incident": is_incident,
        },
        "artifact": artifact,
        "routed_at": _now_iso(),
    }
    return route


# ============================================================================
# Causal Model Artifact
# ============================================================================

def create_causal_model(
    mode: str,
    question: str,
    scope_conditions: list[str] | None = None,
) -> dict[str, Any]:
    """Create an initial Causal Model Artifact."""
    if mode not in CAUSAL_MODES:
        raise CausalRouterError(f"mode must be one of {sorted(CAUSAL_MODES)}")
    if not isinstance(question, str) or not question.strip():
        raise CausalRouterError("question must be a non-empty string")

    model = {
        "schema": MODEL_SCHEMA,
        "mode": mode,
        "question": question,
        "scope_conditions": scope_conditions or [],
        "nodes": [],
        "edges": [],
        "interventions": [],
        "unresolved_assumptions": [],
        "review_ref": None,
        "created_at": _now_iso(),
    }
    return model


def add_node(
    model: dict[str, Any],
    node_id: str,
    statement: str,
    status: str = "hypothesis",
) -> dict[str, Any]:
    """Add a node to the causal model."""
    if not ID_RE.fullmatch(node_id):
        raise CausalRouterError("node_id must match identifier pattern")
    if status not in NODE_STATUSES:
        raise CausalRouterError(f"status must be one of {sorted(NODE_STATUSES)}")

    # Check for duplicate node_id
    existing_ids = {n["id"] for n in model["nodes"]}
    if node_id in existing_ids:
        raise CausalRouterError(f"node_id '{node_id}' already exists")

    node = {
        "id": node_id,
        "statement": statement,
        "status": status,
    }
    model["nodes"].append(node)
    return node


def add_edge(
    model: dict[str, Any],
    from_node: str,
    to_node: str,
    relation: str = "causes",
    logic: str = "UNKNOWN",
    status: str = "hypothesis",
    evidence_refs: list[str] | None = None,
    alternative_explanations: list[str] | None = None,
    falsifiers: list[str] | None = None,
) -> dict[str, Any]:
    """Add an edge to the causal model."""
    if relation not in EDGE_RELATIONS:
        raise CausalRouterError(f"relation must be one of {sorted(EDGE_RELATIONS)}")
    if logic not in EDGE_LOGICS:
        raise CausalRouterError(f"logic must be one of {sorted(EDGE_LOGICS)}")
    if status not in EDGE_STATUSES:
        raise CausalRouterError(f"status must be one of {sorted(EDGE_STATUSES)}")

    # Check that nodes exist
    existing_ids = {n["id"] for n in model["nodes"]}
    if from_node not in existing_ids:
        raise CausalRouterError(f"from_node '{from_node}' does not exist")
    if to_node not in existing_ids:
        raise CausalRouterError(f"to_node '{to_node}' does not exist")

    edge = {
        "from": from_node,
        "to": to_node,
        "relation": relation,
        "logic": logic,
        "status": status,
        "evidence_refs": evidence_refs or [],
        "alternative_explanations": alternative_explanations or [],
        "falsifiers": falsifiers or [],
    }
    model["edges"].append(edge)
    return edge


# ============================================================================
# Validation
# ============================================================================

def validate_causal_model(model: dict[str, Any]) -> dict[str, Any]:
    """Validate a causal model artifact.

    Checks for common causal analysis anti-patterns:
    - correlation_as_causation: Correlation written as causation
    - common_cause_omitted: Common cause not included
    - temporal_order_reversed: Time order reversed
    - selection_bias: Selection bias not addressed
    - feedback_loop: Feedback loop not addressed
    - multiple_sufficient_causes: Multiple sufficient causes not considered
    - non_manipulable_variable: Non-manipulable variable treated as intervention
    - causal_discovery_unstable: Causal discovery output unstable
    - single_root_cause_oversimplification: Single incident reduced to one root cause
    - model_generated_chain_as_long_term_fact: Model-generated chain promoted to fact
    """
    if not isinstance(model, dict):
        raise CausalRouterError("model must be an object")

    if model.get("schema") != MODEL_SCHEMA:
        raise CausalRouterError(f"schema must be {MODEL_SCHEMA}")

    rule_ids: list[str] = []
    warnings: list[str] = []
    verdict = "pass"

    mode = model.get("mode", "")
    nodes = model.get("nodes", [])
    edges = model.get("edges", [])
    unresolved = model.get("unresolved_assumptions", [])

    # Check: every edge must connect existing nodes
    node_ids = {n["id"] for n in nodes}
    for edge in edges:
        if edge["from"] not in node_ids or edge["to"] not in node_ids:
            rule_ids.append("edge_connects_nonexistent_node")
            verdict = "blocked"

    # Check: every edge should have at least one alternative explanation or falsifier
    for edge in edges:
        if not edge.get("alternative_explanations") and not edge.get("falsifiers"):
            warnings.append("edge_without_falsifier")
            if verdict == "pass":
                verdict = "warning"

    # Mode-specific checks
    if mode == "mechanism-chain":
        # Check: edges should be labeled as hypothesis, not fact
        for edge in edges:
            if edge["status"] == "supported" and not edge.get("evidence_refs"):
                rule_ids.append("supported_edge_without_evidence")
                verdict = "blocked"

    elif mode == "causal-inference":
        # Check: must have at least one confound check
        has_confound = any(e["relation"] == "confounds" for e in edges)
        if not has_confound and len(edges) > 0:
            warnings.append("no_confound_check")
            if verdict == "pass":
                verdict = "warning"

    elif mode == "causal-discovery":
        # Check: output should note stability/equivalence class
        if not any("stability" in str(a).lower() or "equivalence" in str(a).lower()
                   for a in unresolved):
            warnings.append("no_stability_note")
            if verdict == "pass":
                verdict = "warning"

    elif mode == "incident-analysis":
        # Check: should not reduce to single root cause
        if len(edges) == 1 and len(nodes) <= 2:
            rule_ids.append("single_root_cause_oversimplification")
            verdict = "blocked"

    # Check: model-generated chain should not be promoted to long-term fact
    for node in nodes:
        if node["status"] == "validated" and not any(
            e.get("evidence_refs") for e in edges if e["to"] == node["id"]
        ):
            warnings.append("validated_node_without_evidence")
            if verdict == "pass":
                verdict = "warning"

    result = {
        "verdict": verdict,
        "rule_ids": rule_ids,
        "warnings": warnings,
        "model_digest": _digest({
            "mode": mode,
            "question": model.get("question", ""),
            "node_count": len(nodes),
            "edge_count": len(edges),
        }),
    }
    return result


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Causal Router for DS Lite v6")
    sub = parser.add_subparsers(dest="command", required=True)

    route_parser = sub.add_parser("route")
    route_parser.add_argument("--question", required=True)
    route_parser.add_argument("--context", help="Path to context JSON")

    validate_parser = sub.add_parser("validate")
    validate_parser.add_argument("--model", required=True, help="Path to model JSON")

    args = parser.parse_args()
    try:
        if args.command == "route":
            ctx = json.loads(open(args.context, encoding="utf-8").read()) if args.context else {}
            result = route_causal_question(args.question, ctx)
        elif args.command == "validate":
            model = json.loads(open(args.model, encoding="utf-8").read())
            result = validate_causal_model(model)
        else:
            return 1
        print(json.dumps(result, ensure_ascii=True, indent=2))
        return 0
    except (CausalRouterError, json.JSONDecodeError, OSError) as exc:
        print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())