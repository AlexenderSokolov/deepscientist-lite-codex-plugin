"""Run the bounded Phase 0/0.5 regression profile and write a redacted receipt."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path


MODULES = (
    "tests.test_communication_hook",
    "tests.test_hooks",
    "tests.test_offline_acceptance",
    "tests.test_user_action_protocol",
    "tests.test_app_server_continuation_acceptance",
    "tests.test_app_server_transport",
    "tests.test_hook_in_turn_repair",
    "tests.test_canonical_thread_smoke",
    "tests.test_control_plane_spike",
    "tests.test_dbos_sqlite_recovery_probe",
    "tests.test_control_plane_incident",
    "tests.test_plugin_packages",
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise RuntimeError("refusing to overwrite phase test receipt")
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    cases = []
    for module in MODULES:
        completed = subprocess.run(
            [sys.executable, "-m", "unittest", module, "-v"],
            text=True, encoding="utf-8", errors="replace", capture_output=True, env=env, check=False,
        )
        output = completed.stdout + completed.stderr
        match = re.search(r"Ran (\d+) tests?", output)
        cases.append({
            "module": module,
            "returncode": completed.returncode,
            "test_count": int(match.group(1)) if match else None,
            "output_sha256": hashlib.sha256(output.encode()).hexdigest(),
            "raw_output_persisted": False,
        })
    receipt = {
        "schema_version": "ds-lite.control-plane-phase-tests.v2",
        "status": "passed" if all(case["returncode"] == 0 for case in cases) else "blocked",
        "cases": cases,
        "release_allowed": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(receipt, handle, indent=2)
        handle.write("\n")
    print(json.dumps({"status": receipt["status"], "module_count": len(cases)}))
    return 0 if receipt["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
