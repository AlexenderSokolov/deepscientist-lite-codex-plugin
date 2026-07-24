from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
STATE_SCRIPT = REPO_ROOT / "plugins" / "deepscientist-lite" / "scripts" / "ds_lite_state.py"


def run_state(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(STATE_SCRIPT), *args, "--root", str(root)],
        cwd=REPO_ROOT,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
    )


class StateArtifactRecoveryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="ds-lite-state-artifact-"))
        initialized = run_state(self.root, "init", "--title", "Recovery", "--question", "Can state be recovered?")
        self.assertEqual(initialized.returncode, 0, initialized.stderr)

    def test_unlinked_artifact_does_not_become_progress_or_evidence(self):
        artifact = self.root / "research" / "artifacts" / "ordinary-output.md"
        artifact.parent.mkdir(parents=True, exist_ok=True)
        artifact.write_text("# Output\nA file exists, but no claim validator ran.\n", encoding="utf-8")

        mission = run_state(self.root, "mission")
        self.assertEqual(mission.returncode, 0, mission.stderr)
        payload = json.loads(mission.stdout)
        self.assertEqual(payload["evidence_strength"], "planning")
        self.assertIn("artifact != progress", payload["readiness_rules"])
        self.assertFalse(payload["waiting_for_user"])

    def test_status_projection_is_rebuilt_from_public_state(self):
        rendered = run_state(self.root, "render-status")
        self.assertEqual(rendered.returncode, 0, rendered.stderr)
        status = (self.root / "STATUS.md").read_text(encoding="utf-8")
        self.assertIn("## Mission Board", status)
        self.assertIn("Next Action", status)

        (self.root / "STATUS.md").write_text("stale hand-edited text\n", encoding="utf-8")
        refreshed = run_state(self.root, "render-status")
        self.assertEqual(refreshed.returncode, 0, refreshed.stderr)
        refreshed_status = (self.root / "STATUS.md").read_text(encoding="utf-8")
        self.assertIn("## Mission Board", refreshed_status)
        self.assertNotIn("stale hand-edited text", refreshed_status)


if __name__ == "__main__":
    unittest.main()
