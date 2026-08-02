"""Prepare a fresh DS Lite workspace for one real Hook-host acceptance run."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CORE_ROOT = REPO_ROOT / "plugins" / "deepscientist-lite-core"
STATE_SCRIPT = CORE_ROOT / "scripts" / "ds_lite_state.py"
SCRIPTS = CORE_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
import ds_lite_iteration  # noqa: E402
import ds_lite_learning  # noqa: E402


class FixtureError(RuntimeError):
    pass


def _terminal_result(after_revision: int) -> dict[str, object]:
    """Return a valid terminal state marked as fixture-prepared, never agent-produced."""
    completed_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return {
        "status": "completed", "after_revision": after_revision, "output_refs": [], "graph_changes": [],
        "validations": [{"command": "fixture-prepared terminal iteration validation", "status": "pass",
                           "summary": "The fixture closed the iteration before the real host turn.", "extensions": {}}],
        "stop_reason": "fixture-prepared-terminal-state",
        "reflection": {
            "observed_outcomes": ["The terminal state was prepared locally for Stop allow acceptance."],
            "hypothesis_updates": [], "expectation_gap": "Agent-initiated terminal closure is not observed by this fixture.",
            "negative_results": [],
            "responsibility": {"authorization_basis": "Real Hook Host B fixture preparation.",
                               "boundaries_respected": ["No provider call or graph mutation was used to close the iteration."],
                               "unresolved_obligations": ["Observe a real host Stop allow decision."], "extensions": {}},
            "learned_boundaries": ["Fixture preparation is not evidence of an agent-initiated closure."],
            "next_candidates": [], "minimal_discriminating_test": "Run one short legal real host turn and record Stop allow.",
            "extensions": {},
        },
        "user_report": {"summary": "Prepared a valid terminal iteration solely for Host B lifecycle acceptance.",
                        "files_changed": [], "validation_summary": "Local terminal iteration validation passed.",
                        "failure_layer": "none", "unverified": ["Agent-initiated terminal closure remains not-observed."],
                        "hypothesis_changes": [], "next_action": "Run the short legal Host B provider turn.",
                        "decision_needed": "none", "extensions": {}},
        "completed_at": completed_at, "extensions": {"fixture_prepared": True},
    }


def prepare(root: Path, *, terminal: bool = False) -> dict[str, object]:
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
    if terminal:
        ds_lite_iteration.finalize_iteration(root, payload["extensions"]["iteration_ref"], _terminal_result(graph["revision"]))
        # This only satisfies the Stop gate's tutorial prerequisite; the receipt
        # and returned metadata prevent treating it as agent-learning evidence.
        ds_lite_learning.learn(
            root, "ds-lite-iterate",
            "适用条件：执行有界科研迭代。关键规则：先登记、后执行、再验证反思并形成终态。"
            "易错点：不得把运行中的 iteration 说成完成，也不得以 fixture 代替 agent 行为。"
            "本任务检查表：确认 iteration 已终态、学习凭证当前、停止事件由真实宿主记录。"
            "仍需人工判断：agent 是否能够在真实任务中自行完成同样的终态闭合。",
            "trusted-hook-host-b-fixture",
        )
    return {"status": "prepared", "workspace_ref": "workspace",
            "iteration_ref": payload["extensions"]["iteration_ref"], "raw_output_persisted": False,
            "terminal_fixture_prepared": terminal,
            "agent_initiated_terminal_closure": "not-observed" if terminal else "not-applicable"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--receipt", required=True)
    parser.add_argument("--terminal", action="store_true",
                        help="Prepare a local terminal state for Host B; not agent-closure evidence.")
    args = parser.parse_args(argv)
    try:
        receipt = prepare(Path(args.workspace), terminal=args.terminal)
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
