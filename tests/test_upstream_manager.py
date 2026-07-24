from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.validation import upstream_manager


ROOT = Path(__file__).resolve().parents[1]


class UpstreamManagerTests(unittest.TestCase):
    def test_inventory_and_verify_cover_vendored_projects(self) -> None:
        inventory = upstream_manager.inventory(ROOT)
        self.assertGreaterEqual(inventory["project_count"], 4)
        audit = upstream_manager.audit(ROOT, check_remote=False)
        self.assertEqual(audit["status"], "passed")
        self.assertFalse(audit["raw_response_persisted"])
        self.assertFalse(audit["secrets_persisted"])

    def test_update_plan_is_read_only_and_fresh_only(self) -> None:
        audit = upstream_manager.audit(ROOT, check_remote=False)
        plan = upstream_manager.update_plan(ROOT, audit)
        self.assertIn("read-only", plan)
        self.assertNotIn(str(ROOT), plan)
        with tempfile.TemporaryDirectory() as raw:
            output = Path(raw) / "plan.md"
            upstream_manager.fresh_write(output, plan)
            with self.assertRaises(upstream_manager.UpstreamError):
                upstream_manager.fresh_write(output, plan)
            self.assertIn("no automatic source update", output.read_text(encoding="utf-8"))

    def test_registry_has_explicit_dispositions(self) -> None:
        registry = json.loads((ROOT / "plugins" / "deepscientist-lite" / "references" / "upstream-project-registry.json").read_text(encoding="utf-8"))
        for project in registry["projects"]:
            self.assertIn(project["disposition"], {"adopted/adapted", "reference-only", "external-only", "rejected"})
            self.assertIn("external_effects", project)


if __name__ == "__main__":
    unittest.main()
