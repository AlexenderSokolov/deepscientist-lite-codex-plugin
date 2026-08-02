"""Run one fresh, read-only provider probe for actual Codex child delegation."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from teaching import fresh_host_probe, trusted_host_prepare


PROMPT = (
    "Use exactly two child agents for two independent, read-only checks. "
    "Child A must report the first heading in PROJECT.md. Child B must report the first heading in README.md. "
    "Do not delegate from a child. Do not modify files, run commands, access the network, or use browser tools. "
    "As the parent, compare the two returned headings in one sentence and stop."
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run one fresh real two-child delegation canary.")
    parser.add_argument("--codex-bin", type=Path, required=True)
    parser.add_argument("--source-home", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--pilot-root", type=Path, required=True)
    parser.add_argument("--timeout-seconds", type=float, default=180.0)
    args = parser.parse_args(argv)
    output = args.pilot_root / "delegation-canary.json"
    try:
        trusted_host_prepare.prepare(
            codex_bin=args.codex_bin,
            source_home=args.source_home,
            repo_root=args.repo_root,
            pilot_root=args.pilot_root,
        )
        host = fresh_host_probe.run_once(
            codex_bin=args.codex_bin,
            codex_home=args.pilot_root / "codex-home",
            workspace=args.pilot_root / "workspace",
            hook_events_path=args.pilot_root / "hook-events",
            prompt=PROMPT,
            output_path=args.pilot_root / "host.json",
            timeout_seconds=args.timeout_seconds,
            bypass_hook_trust=True,
            expected_cli_version=trusted_host_prepare.EXPECTED_VERSION,
            expected_cli_sha256=trusted_host_prepare.EXPECTED_SHA256,
        )
        collab = host.get("collaboration", {})
        passed = (
            host.get("status") == "passed"
            and collab.get("spawn_count") == 2
            and collab.get("receiver_count") == 2
            and collab.get("tool_counts", {}).get("spawn_agent") == 2
            and collab.get("status_counts", {}).get("completed", 0) >= 2
        )
        receipt = {
            "schema_version": "ds-lite.real-delegation-canary.v1",
            "status": "passed" if passed else "blocked",
            "host_receipt_ref": "host.json",
            "spawn_agent_count": collab.get("spawn_count", 0),
            "receiver_count": collab.get("receiver_count", 0),
            "receiver_id_sha256": collab.get("receiver_id_sha256", []),
            "nested_delegation": "not-observed",
            "workspace_writes": "not-allowed",
            "automatic_retry_observed": False,
            "next_action": "run full delegation contract" if passed else "freeze this canary and inspect the redacted host receipt",
        }
        if output.exists():
            raise RuntimeError("delegation canary output already exists")
        output.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    except Exception as exc:
        print(f"real delegation canary failed: {type(exc).__name__}", file=sys.stderr)
        return 1
    print(json.dumps({"status": receipt["status"], "spawn_agent_count": receipt["spawn_agent_count"]}))
    return 0 if receipt["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
