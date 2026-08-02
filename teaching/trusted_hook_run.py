"""Run one trusted-host probe through a stable argv-only CLI boundary."""
from __future__ import annotations
import argparse
import hashlib
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from teaching.fresh_host_probe import run_once

EXPECTED_SHA256 = "EFDB3540EF74B9909408C8D38DA79483454797B36F471E3E004FC2BF2B70E22A"
EXPECTED_CODEX_VERSION = "0.144.5"


def evaluate_hook_continuation(receipt: dict[str, object]) -> dict[str, object]:
    event_counts = receipt.get("event_type_counts")
    event_counts = event_counts if isinstance(event_counts, dict) else {}
    sequence = receipt.get("hook_event_sequence")
    sequence = sequence if isinstance(sequence, list) else []
    stops = [item for item in sequence if isinstance(item, dict) and item.get("event_type") == "stop"]
    identity = receipt.get("cli_identity")
    identity = identity if isinstance(identity, dict) else {}
    checks = {
        "runtime_pin_enforced": identity.get("enforced") is True and identity.get("sha256_match") is True,
        "one_cli_turn": event_counts.get("turn.started") == 1,
        "one_terminal_turn": event_counts.get("turn.completed") == 1,
        "terminal_observed": receipt.get("terminal_event_observed") is True,
        "stop_block_then_allow": [item.get("decision") for item in stops] == ["block", "allow"],
        "nonempty_stop_reasons": len(stops) == 2 and all(item.get("reason_present") is True for item in stops),
        "repair_budget_transition": (
            len(stops) == 2
            and stops[0].get("stop_hook_active") is False
            and stops[1].get("stop_hook_active") is True
        ),
        "same_cli_turn_repair": (
            event_counts.get("turn.started") == 1
            and [item.get("decision") for item in stops] == ["block", "allow"]
        ),
    }
    return {
        "schema_version": "ds-lite.phase5-hook-continuation-verifier.v1",
        "status": "passed" if receipt.get("status") == "passed" and all(checks.values()) else "failed",
        "checks": checks,
        "evidence_class": "real-codex-cli",
        "hook_trust_mode": "isolated-vetted-bypass",
        "persisted_global_hook_trust": False,
        "release_allowed": False,
    }

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    for name in ("codex-bin", "codex-home", "workspace", "hook-events", "output", "prompt"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--verification-output")
    parser.add_argument("--expected-version", default=EXPECTED_CODEX_VERSION)
    parser.add_argument("--expected-sha256", default=EXPECTED_SHA256)
    args = parser.parse_args(argv)
    values = [args.codex_bin, args.codex_home, args.workspace, args.hook_events, args.output]
    if any("<" in value or ">" in value for value in values):
        print("placeholder path is not allowed", file=sys.stderr); return 2
    binary = Path(args.codex_bin).resolve()
    directories = [Path(args.codex_home).resolve(), Path(args.workspace).resolve(),
                   Path(args.hook_events).resolve()]
    if not binary.is_file() or any(not path.is_dir() for path in directories):
        print("required host path does not exist", file=sys.stderr); return 2
    expected_sha256 = args.expected_sha256.upper()
    if hashlib.sha256(binary.read_bytes()).hexdigest().upper() != expected_sha256:
        print("Codex binary SHA-256 mismatch; refusing real host execution", file=sys.stderr); return 1
    try:
        receipt = run_once(codex_bin=binary, codex_home=directories[0], workspace=directories[1],
                           hook_events_path=directories[2], output_path=Path(args.output).resolve(),
                           prompt=args.prompt, bypass_hook_trust=True,
                           expected_cli_version=args.expected_version,
                           expected_cli_sha256=expected_sha256)
    except Exception as exc:
        print(f"hook probe failed: {type(exc).__name__}", file=sys.stderr); return 1
    verification = evaluate_hook_continuation(receipt)
    if args.verification_output:
        verification_output = Path(args.verification_output).resolve()
        verification_output.parent.mkdir(parents=True, exist_ok=True)
        with verification_output.open("x", encoding="utf-8", newline="\n") as handle:
            json.dump(verification, handle, indent=2, sort_keys=True)
            handle.write("\n")
    print(json.dumps({"status": verification["status"], "failure_layer": receipt["failure_layer"],
                      "hook_event_count": len(receipt.get("hook_events", []))}))
    return 0 if verification["status"] == "passed" else 1

if __name__ == "__main__":
    raise SystemExit(main())
