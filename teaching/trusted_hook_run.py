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

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    for name in ("codex-bin", "codex-home", "workspace", "hook-events", "output", "prompt"):
        parser.add_argument("--" + name, required=True)
    args = parser.parse_args(argv)
    values = [args.codex_bin, args.codex_home, args.workspace, args.hook_events, args.output]
    if any("<" in value or ">" in value for value in values):
        print("placeholder path is not allowed", file=sys.stderr); return 2
    binary = Path(args.codex_bin)
    directories = [Path(args.codex_home), Path(args.workspace), Path(args.hook_events)]
    if not binary.is_file() or any(not path.is_dir() for path in directories):
        print("required host path does not exist", file=sys.stderr); return 2
    if hashlib.sha256(binary.read_bytes()).hexdigest().upper() != EXPECTED_SHA256:
        print("Codex binary SHA-256 mismatch; refusing real host execution", file=sys.stderr); return 1
    try:
        receipt = run_once(codex_bin=binary, codex_home=directories[0], workspace=directories[1],
                           hook_events_path=directories[2], output_path=Path(args.output),
                           prompt=args.prompt, bypass_hook_trust=True,
                           expected_cli_version=EXPECTED_CODEX_VERSION,
                           expected_cli_sha256=EXPECTED_SHA256)
    except Exception as exc:
        print(f"hook probe failed: {type(exc).__name__}", file=sys.stderr); return 1
    print(json.dumps({"status": receipt["status"], "failure_layer": receipt["failure_layer"],
                      "hook_event_count": len(receipt.get("hook_events", []))}))
    return 0 if receipt["status"] == "passed" else 1

if __name__ == "__main__":
    raise SystemExit(main())
