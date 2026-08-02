"""Prepare one fresh workspace for app-server autonomy-continuation acceptance."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from teaching import trusted_hook_fixture


class FixtureError(RuntimeError):
    pass


def prepare(workspace: Path) -> dict[str, object]:
    if not workspace.is_dir():
        raise FixtureError("workspace directory does not exist")
    prepared = trusted_hook_fixture.prepare(workspace, terminal=False)
    audit = subprocess.run(
        [sys.executable, str(trusted_hook_fixture.CORE_ROOT / "scripts" / "ds_lite_communication_audit.py"),
         "init", "--root", str(workspace), "--skill", "ds-lite-iterate",
         "--task-class", "repository-change", "--id", "appserver-continuation"],
        cwd=REPO_ROOT, text=True, encoding="utf-8", errors="replace",
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
    )
    if audit.returncode != 0:
        raise FixtureError("communication audit initialization failed")
    autonomy = workspace / "research" / "autonomy"
    autonomy.mkdir(parents=True, exist_ok=False)
    (autonomy / "approval.md").write_text("approved isolated continuation acceptance\n", encoding="utf-8")
    (autonomy / "stop-first.json").write_text(
        json.dumps({"schema_version": "ds-lite.stop-first-protocol.v1", "status": "prepared"}) + "\n",
        encoding="utf-8",
    )
    gate_script = autonomy / "complete_gate.py"
    gate_script.write_text(
        "import json\nimport sys\nfrom datetime import datetime, timezone\nfrom pathlib import Path\n"
        "root = Path.cwd()\n"
        "path = Path(sys.argv[1])\npath.parent.mkdir(parents=True, exist_ok=True)\n"
        "path.write_text(json.dumps({'status': 'passed', 'failure_layer': 'none'}) + '\\n', encoding='utf-8')\n"
        "work_unit = json.loads((root / 'research' / 'work-unit.json').read_text(encoding='utf-8'))\n"
        "iteration_path = root / work_unit['active_iteration_ref']\n"
        "iteration = json.loads(iteration_path.read_text(encoding='utf-8'))\n"
        "revision = json.loads((root / 'research' / 'state' / 'graph.json').read_text(encoding='utf-8'))['revision']\n"
        "iteration.update({'status': 'completed', 'after_revision': revision, 'completed_at': datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z'), 'stop_reason': 'autonomy-controller-completed', 'output_refs': ['research/autonomy/gate-receipt.json']})\n"
        "iteration['reflection'].update({'observed_outcomes': ['The approved autonomy gate completed.'], 'learned_boundaries': ['Stop closure requires a terminal controller summary.'], 'minimal_discriminating_test': 'Attempt Stop after the controller summary.'})\n"
        "iteration['reflection']['responsibility'].update({'authorization_basis': 'research/autonomy/approval.md', 'boundaries_respected': ['one approved gate', 'no release action'], 'unresolved_obligations': []})\n"
        "iteration['user_report'].update({'summary': 'Autonomy controller completed the isolated continuation gate.', 'validation_summary': 'gate receipt status passed', 'failure_layer': 'none', 'next_action': 'attempt Stop again', 'decision_needed': ''})\n"
        "iteration_path.write_text(json.dumps(iteration, ensure_ascii=False, indent=2) + '\\n', encoding='utf-8')\n",
        encoding="utf-8",
    )
    contract = {
        "schema_version": "ds-lite.autonomy-contract.v1",
        "autonomy_id": "appserver-continuation",
        "status": "prepared",
        "goals": ["appserver-continuation"],
        "gates": [{
            "id": "continuation",
            "depends_on": [],
            "command": ["python", "research/autonomy/complete_gate.py", "research/autonomy/gate-receipt.json"],
            "receipt_ref": "research/autonomy/gate-receipt.json",
            "retry_class": "none",
        }],
        "budget": {"max_attempts_per_gate": 3, "max_seconds": 60},
        "authorization": {"status": "approved", "authority": "user", "ref": "research/autonomy/approval.md"},
        "release": {"authorized": True, "required_gates": ["continuation"]},
    }
    (autonomy / "contract.json").write_text(json.dumps(contract, indent=2) + "\n", encoding="utf-8")
    return {**prepared, "communication_audit_prepared": True,
            "autonomy_contract_prepared": True, "autonomy_gate_count": 1}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--receipt", required=True, type=Path)
    args = parser.parse_args()
    if args.receipt.exists():
        raise SystemExit("fixture receipt already exists; refusing overwrite")
    try:
        receipt = prepare(args.workspace)
    except (FixtureError, trusted_hook_fixture.FixtureError, OSError, ValueError, KeyError) as exc:
        print(f"fixture preparation failed: {type(exc).__name__}")
        return 1
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": receipt["status"], "autonomy_contract_prepared": True}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
