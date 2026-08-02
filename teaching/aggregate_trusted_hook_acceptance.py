"""Combine two frozen trusted-host Hook pilots without changing their evidence."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


EXPECTED_VERSION = "0.144.5"
HOOK_SCHEMA = "ds-lite.trusted-hook-acceptance.v1"


class AcceptanceError(RuntimeError):
    pass


def _read(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise AcceptanceError(f"cannot read acceptance evidence: {path.name}") from exc
    if not isinstance(value, dict):
        raise AcceptanceError("acceptance evidence must be a JSON object")
    return value


def _events(receipt: dict[str, Any]) -> set[tuple[str, str]]:
    raw = receipt.get("hook_events")
    if not isinstance(raw, list):
        raise AcceptanceError("fresh-host receipt has no Hook events")
    observed: set[tuple[str, str]] = set()
    for item in raw:
        if not isinstance(item, dict):
            raise AcceptanceError("Hook event is invalid")
        event_type, decision = item.get("event_type"), item.get("decision")
        if event_type not in {"user-prompt-submit", "pre-tool-use", "post-tool-use", "stop"}:
            raise AcceptanceError("Hook event type is invalid")
        if decision not in {"allow", "block"}:
            raise AcceptanceError("Hook decision is invalid")
        observed.add((event_type, decision))
    return observed


def _validate_host(receipt: dict[str, Any]) -> None:
    identity = receipt.get("cli_identity")
    if not isinstance(identity, dict) or identity.get("expected_version") != EXPECTED_VERSION:
        raise AcceptanceError("fresh-host receipt has the wrong Codex identity")
    if receipt.get("status") != "passed" or receipt.get("failure_layer") != "none":
        raise AcceptanceError("fresh-host probe did not pass")
    if receipt.get("automatic_retry_observed") is not False or receipt.get("raw_output_persisted") is not False:
        raise AcceptanceError("fresh-host receipt violates retry or redaction boundary")


def aggregate(host_a_path: Path, host_b_path: Path, fixture_b_path: Path) -> dict[str, Any]:
    host_a, host_b, fixture_b = _read(host_a_path), _read(host_b_path), _read(fixture_b_path)
    _validate_host(host_a)
    _validate_host(host_b)
    a_events, b_events = _events(host_a), _events(host_b)
    required_a = {("user-prompt-submit", "allow"), ("pre-tool-use", "block"),
                  ("post-tool-use", "allow"), ("stop", "block")}
    required_b = {("user-prompt-submit", "allow"), ("pre-tool-use", "allow"),
                  ("post-tool-use", "allow"), ("stop", "allow")}
    if not required_a.issubset(a_events):
        raise AcceptanceError("Host A does not prove the unsafe-operation and first-stop blocks")
    if not required_b.issubset(b_events):
        raise AcceptanceError("Host B does not prove legal lifecycle allow decisions")
    if fixture_b.get("terminal_fixture_prepared") is not True:
        raise AcceptanceError("Host B terminal fixture was not explicitly recorded")
    if fixture_b.get("agent_initiated_terminal_closure") != "not-observed":
        raise AcceptanceError("fixture must not claim agent-initiated terminal closure")
    return {
        "schema_version": HOOK_SCHEMA,
        "status": "passed",
        "codex_version": EXPECTED_VERSION,
        "host_a": {"role": "unsafe-action-and-first-stop-block", "receipt_ref": host_a_path.name},
        "host_b": {"role": "fixture-prepared-terminal-stop-allow", "receipt_ref": host_b_path.name,
                   "fixture_ref": fixture_b_path.name},
        "observed": {
            "user_prompt_submit_allow": True,
            "pre_tool_use_block": True,
            "post_tool_use_allow": True,
            "stop_first_block": True,
            "stop_closed_allow": True,
        },
        "agent_initiated_terminal_closure": "not-observed",
        "automatic_retry_observed": False,
        "raw_prompt_or_event_stream_persisted": False,
        "limitations": ["Host B terminal closure was fixture-prepared before the real provider turn."],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Aggregate frozen Host A and Host B Hook receipts.")
    parser.add_argument("--host-a", type=Path, required=True)
    parser.add_argument("--host-b", type=Path, required=True)
    parser.add_argument("--fixture-b", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.output.exists():
        print("output already exists; refusing overwrite", file=sys.stderr)
        return 2
    try:
        payload = aggregate(args.host_a, args.host_b, args.fixture_b)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    except (AcceptanceError, OSError, UnicodeError) as exc:
        print(f"Hook acceptance aggregation failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({"status": payload["status"], "schema_version": payload["schema_version"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
