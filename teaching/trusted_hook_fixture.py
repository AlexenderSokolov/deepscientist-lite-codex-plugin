"""Prepare a fresh DS Lite workspace for one real Hook-host acceptance run."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
STATE_SCRIPT = REPO_ROOT / "plugins" / "deepscientist-lite" / "scripts" / "ds_lite_state.py"
SCRIPTS = REPO_ROOT / "plugins" / "deepscientist-lite" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
import ds_lite_iteration  # noqa: E402


class FixtureError(RuntimeError):
    pass


def prepare(root: Path) -> dict[str, object]:
    if not root.is_dir():
        raise FixtureError("workspace directory does not exist")
    required = (root / "PROJECT.md", root / "research" / "state" / "graph.json", root / "research" / "work-unit.json")
    if any(path.exists() for path in required):
        raise FixtureError("workspace fixture already exists; refusing overwrite")
    completed = subprocess.run(
        [sys.executable, str(STATE_SCRIPT), "init", "--root", str(root),
         "--title", "Trusted Hook acceptance fixture",
         "--question", "Can one bounded iteration be protected by the real Hook host?",
         "--no-render"],
        cwd=REPO_ROOT, text=True, encoding="utf-8", errors="replace",
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
    )
    if completed.returncode != 0:
        raise FixtureError("DS Lite state initialization failed")
    graph = json.loads((root / "research" / "state" / "graph.json").read_text(encoding="utf-8"))
    payload = ds_lite_iteration.initialize_iteration(
        root, iteration_id="trusted-hook-running-01", selected_skill="ds-lite-iterate",
        action={
            "kind": "execute",
            "summary": "Exercise real Hook decisions for one bounded iteration.",
            "prediction": "The Hook host will block unsafe graph edits and one incomplete stop.",
            "falsification_condition": "A required event is absent or an unsafe operation is allowed.",
            "resource_limits": [{"dimension": "actions", "unit": "count", "value": 1}],
            "stop_condition": "Stop after the host records the required event sequence.",
            "extensions": {},
        }, input_refs=["PROJECT.md", "research/work-unit.json"], expected_revision=graph["revision"],
    )
    return {"status": "prepared", "workspace_ref": "workspace",
            "iteration_ref": payload["extensions"]["iteration_ref"], "raw_output_persisted": False}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--receipt", required=True)
    args = parser.parse_args(argv)
    try:
        receipt = prepare(Path(args.workspace))
        output = Path(args.receipt)
        if output.exists():
            raise FixtureError("fixture receipt already exists; refusing overwrite")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8", newline="\n")
    except (FixtureError, OSError, UnicodeError, ValueError, KeyError) as exc:
        print(f"hook fixture preparation failed: {type(exc).__name__}", file=sys.stderr)
        return 1
    print(json.dumps({"status": receipt["status"], "iteration_ref": receipt["iteration_ref"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
