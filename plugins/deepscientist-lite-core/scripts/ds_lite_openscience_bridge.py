#!/usr/bin/env python3
"""OpenScience File/CLI Bridge for DS Lite v6.

Implements Mission/Return interoperation between OpenScience and DS Lite
without shared databases, daemon processes, or A2A network services.

Schema: ds-lite.openscience-bridge.v1
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path
from typing import Any

BRIDGE_SCHEMA = "ds-lite.openscience-bridge.v1"
ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,79}$")

MANIFEST_STATUSES = frozenset({
    "active", "completed", "failed", "superseded",
})

RETURN_STATUSES = frozenset({
    "success", "partial", "failed", "blocked",
})

ORDER_STATUSES = frozenset({
    "received", "accepted", "executing", "returned", "rejected",
})


class BridgeError(RuntimeError):
    pass


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _digest(data: dict[str, Any]) -> str:
    canonical = json.dumps(data, sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# ============================================================================
# Capability Manifest
# ============================================================================

def export_capability_manifest(project: dict[str, Any], now: str | None = None) -> dict[str, Any]:
    """Export a capability manifest for OpenScience discovery.

    The manifest describes what DS Lite can do without exposing internal
    state, credentials, or private data.
    """
    if not isinstance(project, dict):
        raise BridgeError("project must be an object")

    project_id = project.get("project_id", "")
    if not ID_RE.fullmatch(project_id):
        raise BridgeError("project.project_id must match identifier pattern")

    timestamp = now or _now_iso()

    manifest = {
        "schema_version": BRIDGE_SCHEMA,
        "manifest_id": f"manifest-{project_id}-{timestamp.replace(':', '-').replace('-', '')[:16]}",
        "project_id": project_id,
        "capabilities": project.get("capabilities", [
            "task-assessment",
            "experiment-execution",
            "evidence-collection",
            "claim-validation",
            "quality-review",
        ]),
        "supported_protocols": ["ds-lite.mission-order.v1", "ds-lite.return-pack.v1"],
        "constraints": {
            "max_concurrent_missions": 1,
            "requires_authority_digest": True,
            "requires_acceptance_criteria": True,
            "requires_stop_conditions": True,
        },
        "status": "active",
        "exported_at": timestamp,
        "extensions": {},
    }
    return manifest


# ============================================================================
# Mission Order Import
# ============================================================================

def import_order(order: dict[str, Any], project: dict[str, Any]) -> dict[str, Any]:
    """Import a mission order from OpenScience.

    Key rule: Duplicate delivery is idempotent - the same order delivered
    twice should produce the same mission_id and not create a new work unit.

    Returns an ImportResult with:
    - mission_id: str
    - created_new_work_unit: bool
    - import_status: str
    - import_digest: str
    """
    if not isinstance(order, dict):
        raise BridgeError("order must be an object")
    if not isinstance(project, dict):
        raise BridgeError("project must be an object")

    # Validate order has required fields
    required_order_fields = {"mission_id", "objective", "authority_digest"}
    missing = required_order_fields - set(order.keys())
    if missing:
        raise BridgeError(f"order missing required fields: {sorted(missing)}")

    order_mission_id = order["mission_id"]
    if not isinstance(order_mission_id, str) or not ID_RE.fullmatch(order_mission_id):
        raise BridgeError("order.mission_id must match identifier pattern")

    # Check for duplicate delivery (idempotency)
    existing_missions = project.get("_existing_missions", {})
    if order_mission_id in existing_missions:
        # Idempotent: return existing mission without creating new work unit
        existing = existing_missions[order_mission_id]
        return {
            "mission_id": existing["mission_id"],
            "created_new_work_unit": False,
            "import_status": "idempotent_duplicate",
            "import_digest": existing.get("import_digest", ""),
        }

    # Create new work unit
    import_data = {
        "mission_id": order_mission_id,
        "objective": order.get("objective", ""),
        "authority_digest": order.get("authority_digest", ""),
        "project_id": project.get("project_id", ""),
    }
    import_digest = _digest(import_data)

    result = {
        "mission_id": order_mission_id,
        "created_new_work_unit": True,
        "import_status": "received",
        "import_digest": import_digest,
    }
    return result


# ============================================================================
# Mission Return Export
# ============================================================================

def export_return(mission: dict[str, Any], evidence: dict[str, Any]) -> dict[str, Any]:
    """Export a mission return pack for OpenScience.

    The return pack contains evidence, limitations, and next decisions
    without exposing internal state or credentials.
    """
    if not isinstance(mission, dict):
        raise BridgeError("mission must be an object")
    if not isinstance(evidence, dict):
        raise BridgeError("evidence must be an object")

    mission_id = mission.get("mission_id", "")
    if not ID_RE.fullmatch(mission_id):
        raise BridgeError("mission.mission_id must match identifier pattern")

    # Determine return status based on evidence
    has_success = evidence.get("has_success", False)
    has_failure = evidence.get("has_failure", False)
    has_blocker = evidence.get("has_blocker", False)

    if has_blocker:
        return_status = "blocked"
    elif has_success and not has_failure:
        return_status = "success"
    elif has_success and has_failure:
        return_status = "partial"
    else:
        return_status = "failed"

    return_pack = {
        "schema_version": BRIDGE_SCHEMA,
        "return_id": f"return-{mission_id}-{_now_iso().replace(':', '-').replace('-', '')[:16]}",
        "mission_id": mission_id,
        "return_status": return_status,
        "evidence_summary": {
            "total_evidence": evidence.get("total_evidence", 0),
            "passed_checks": evidence.get("passed_checks", 0),
            "failed_checks": evidence.get("failed_checks", 0),
        },
        "limitations": evidence.get("limitations", []),
        "next_decisions": evidence.get("next_decisions", []),
        "exported_at": _now_iso(),
        "extensions": {},
    }

    # Compute return digest
    return_pack["return_digest"] = _digest({
        "return_id": return_pack["return_id"],
        "mission_id": mission_id,
        "return_status": return_status,
    })

    return return_pack


# ============================================================================
# Bridge Validation
# ============================================================================

def validate_bridge_config(config: dict[str, Any]) -> dict[str, Any]:
    """Validate a bridge configuration.

    Ensures:
    - No shared database between OpenScience and DS Lite
    - No daemon process
    - No A2A network service
    - Platform unavailable does not break standalone
    """
    if not isinstance(config, dict):
        raise BridgeError("config must be an object")

    rule_ids: list[str] = []
    verdict = "pass"

    # Check: no shared database
    if config.get("shared_database", False):
        rule_ids.append("shared_database_detected")
        verdict = "blocked"

    # Check: no daemon
    if config.get("daemon_enabled", False):
        rule_ids.append("daemon_enabled_detected")
        verdict = "blocked"

    # Check: no A2A network service
    if config.get("a2a_network_service", False):
        rule_ids.append("a2a_network_service_detected")
        verdict = "blocked"

    # Check: standalone fallback exists
    if not config.get("standalone_fallback", False):
        rule_ids.append("standalone_fallback_missing")
        verdict = "blocked"

    result = {
        "verdict": verdict,
        "rule_ids": rule_ids,
    }
    return result


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="OpenScience File/CLI Bridge for DS Lite v6")
    sub = parser.add_subparsers(dest="command", required=True)

    export_manifest_parser = sub.add_parser("export-manifest")
    export_manifest_parser.add_argument("--project", required=True, help="Path to project JSON")

    import_order_parser = sub.add_parser("import-order")
    import_order_parser.add_argument("--order", required=True)
    import_order_parser.add_argument("--project", required=True)

    export_return_parser = sub.add_parser("export-return")
    export_return_parser.add_argument("--mission", required=True)
    export_return_parser.add_argument("--evidence", required=True)

    args = parser.parse_args()
    try:
        if args.command == "export-manifest":
            project = json.loads(open(args.project, encoding="utf-8").read())
            result = export_capability_manifest(project)
        elif args.command == "import-order":
            order = json.loads(open(args.order, encoding="utf-8").read())
            project = json.loads(open(args.project, encoding="utf-8").read())
            result = import_order(order, project)
        elif args.command == "export-return":
            mission = json.loads(open(args.mission, encoding="utf-8").read())
            evidence = json.loads(open(args.evidence, encoding="utf-8").read())
            result = export_return(mission, evidence)
        else:
            return 1
        print(json.dumps(result, ensure_ascii=True, indent=2))
        return 0
    except (BridgeError, json.JSONDecodeError, OSError) as exc:
        print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())