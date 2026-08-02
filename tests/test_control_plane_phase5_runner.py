from __future__ import annotations

import shutil
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INPUT_NAMES = {
    "runtime-windows", "runtime-linux", "resource-windows", "resource-linux",
    "stable-hook", "stable-v2-action", "dbos-upgrade", "supervisor-windows",
    "supervisor-wsl", "real-host-chaos", "network-matrix", "synthetic-provider",
    "fresh-desktop", "openscience", "matched-effect", "backup-restore",
}


class Phase5RunnerContractTests(unittest.TestCase):
    def test_bash_runner_is_fail_closed_final_assembly_only(self) -> None:
        path = ROOT / "tools" / "validation" / "runners" / "run_control_plane_phase5.sh"
        text = path.read_text(encoding="ascii")
        self.assertIn("set -euo pipefail", text)
        self.assertIn('codex_version="0.146.0"', text)
        self.assertIn("dbos-2.29.0.dist-info", text)
        self.assertIn("package-manifest", text)
        self.assertIn(" candidate ", text)
        self.assertIn(" evidence ", text)
        self.assertIn(" gate ", text)
        self.assertIn(" aggregate ", text)
        self.assertIn(" decision ", text)
        self.assertIn("evidence root already exists", text.lower())
        self.assertIn("--phase4-decision-sha256", text)
        self.assertNotIn("--control-aggregate", text)
        for name in INPUT_NAMES:
            self.assertIn(name, text)
        for forbidden in ("real_host.py", "chaos_matrix.py", "provider", "curl ", "wget "):
            if forbidden == "provider":
                continue
            self.assertNotIn(forbidden, text)

    def test_powershell_runner_has_equivalent_contract(self) -> None:
        path = ROOT / "tools" / "validation" / "runners" / "run_control_plane_phase5.ps1"
        text = path.read_text(encoding="ascii")
        self.assertIn('$ErrorActionPreference = "Stop"', text)
        self.assertIn('$CodexVersion = "0.146.0"', text)
        self.assertIn("dbos-2.29.0.dist-info", text)
        self.assertIn("Phase4DecisionSha256", text)
        for command in ("package-manifest", "candidate", "evidence", "gate", "aggregate", "decision"):
            self.assertIn(command, text)
        for name in INPUT_NAMES:
            self.assertIn(name, text)

    def test_shell_syntax_when_interpreters_are_available(self) -> None:
        bash = shutil.which("bash")
        if bash:
            probe = subprocess.run([bash, "--version"], capture_output=True)
            if probe.returncode == 0:
                subprocess.run([bash, "-n", str(ROOT / "tools" / "validation" / "runners" / "run_control_plane_phase5.sh")], check=True)
        powershell = shutil.which("powershell") or shutil.which("pwsh")
        if powershell:
            probe = subprocess.run([powershell, "-NoProfile", "-Command", "$PSVersionTable.PSVersion"], capture_output=True)
            if probe.returncode == 0:
                script = str(ROOT / "tools" / "validation" / "runners" / "run_control_plane_phase5.ps1").replace("'", "''")
                command = f"[scriptblock]::Create((Get-Content -Raw -LiteralPath '{script}')) | Out-Null"
                subprocess.run([
                    powershell, "-NoProfile", "-Command", command,
                ], check=True)


if __name__ == "__main__":
    unittest.main()
