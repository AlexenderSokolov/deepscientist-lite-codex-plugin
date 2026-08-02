"""Fail-closed verifier for a real Hook in-turn repair observation."""

from __future__ import annotations


def evaluate_observation(observation: dict, *, schema_digest: str) -> dict:
    receipt = {
        "schema_version": "ds-lite.hook-in-turn-repair.v1",
        "status": "blocked",
        "failure_layer": "real-host-not-observed",
        "deterministic_verifier": False,
        "release_evidence": False,
        "release_allowed": False,
    }
    if not isinstance(observation, dict) or observation.get("evidence_class") != "real-host":
        return receipt
    if observation.get("schema_digest") != schema_digest:
        receipt["failure_layer"] = "schema-digest-mismatch"
        return receipt
    if observation.get("controller_turn_start_count") != 1:
        receipt["failure_layer"] = "controller-turn-count"
        return receipt
    stop_events = observation.get("stop_events")
    if not isinstance(stop_events, list) or len(stop_events) != 2 or not all(isinstance(event, dict) for event in stop_events):
        receipt["failure_layer"] = "stop-event-count"
        return receipt
    first, second = stop_events
    first_turn = first.get("turn_id")
    second_turn = second.get("turn_id")
    if not isinstance(first_turn, str) or not first_turn or first_turn != second_turn:
        receipt["failure_layer"] = "turn-identity"
        return receipt
    for event in (first, second):
        if not isinstance(event.get("reason"), str) or not event["reason"].strip():
            receipt["failure_layer"] = "stop-reason"
            return receipt
    if first.get("decision") != "block" or first.get("stop_hook_active") is not False:
        receipt["failure_layer"] = "first-stop-shape"
        return receipt
    if second.get("decision") != "allow" or second.get("stop_hook_active") is not True:
        receipt["failure_layer"] = "second-stop-shape"
        return receipt
    terminal = observation.get("terminal")
    if not isinstance(terminal, dict) or terminal.get("kind") != "hook_handoff" or terminal.get("turn_id") != first_turn:
        receipt["failure_layer"] = "terminal-handoff"
        return receipt
    receipt.update({
        "status": "passed",
        "failure_layer": "none",
        "deterministic_verifier": True,
        "phase_gate_evidence": True,
        "verified_turn_id": first_turn,
    })
    return receipt
