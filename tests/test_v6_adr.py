#!/usr/bin/env python3
"""Document test: assert ADR contains all 35 fixed design decisions."""

import unittest
from pathlib import Path

ADR_PATH = Path(__file__).resolve().parents[1] / "docs" / "adr" / "ADR-v6-research-kernel-and-control-boundary.md"


class ADRDocumentTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(ADR_PATH.exists(), f"ADR not found at {ADR_PATH}")
        self.content = ADR_PATH.read_text(encoding="utf-8")

    def test_adr_contains_35_decisions(self):
        for i in range(1, 36):
            self.assertIn(f"{i}. ", self.content, f"Decision {i} not found in ADR")

    def test_adr_contains_phase3_status(self):
        self.assertIn("Phase 3", self.content)
        self.assertIn("NOT passed", self.content)

    def test_adr_contains_no_daemon(self):
        self.assertIn("no daemon", self.content)

    def test_adr_contains_graph_authority(self):
        self.assertIn("Graph Authority", self.content)

    def test_adr_contains_frontier_non_authority(self):
        self.assertIn("Frontier Non-Authority", self.content)

    def test_adr_contains_task_assessment_embedded(self):
        self.assertIn("Task Assessment Embedded in Contract", self.content)

    def test_adr_contains_v1_compatibility(self):
        self.assertIn("v1 Compatibility", self.content)

    def test_adr_contains_controller_scientific_boundary(self):
        self.assertIn("Controller Scientific Boundary", self.content)


if __name__ == "__main__":
    unittest.main()