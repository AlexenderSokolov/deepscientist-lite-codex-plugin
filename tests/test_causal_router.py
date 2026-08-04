#!/usr/bin/env python3
"""Tests for Causal Router (Causal Router PR)."""

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from plugins.deepscientist_lite_import_shim import ds_lite_causal_router


class CausalRouterTests(unittest.TestCase):
    def test_route_to_causal_inference(self):
        """Should route to causal-inference when numerical effect is needed."""
        route = ds_lite_causal_router.route_causal_question(
            "What is the effect of treatment X on outcome Y?",
            context={"needs_numerical_effect": True},
        )
        self.assertEqual(route["mode"], "causal-inference")

    def test_route_to_mechanism_chain(self):
        """Should route to mechanism-chain when mechanism is known."""
        route = ds_lite_causal_router.route_causal_question(
            "How can we find more intervention points for known mechanism?",
            context={"mechanism_known": True},
        )
        self.assertEqual(route["mode"], "mechanism-chain")

    def test_route_to_causal_discovery(self):
        """Should route to causal-discovery when data is available."""
        route = ds_lite_causal_router.route_causal_question(
            "What structures in the data are worth forming hypotheses?",
            context={"has_data": True, "accepts_exploratory": True},
        )
        self.assertEqual(route["mode"], "causal-discovery")

    def test_route_to_incident_analysis(self):
        """Should route to incident-analysis for failure复盘."""
        route = ds_lite_causal_router.route_causal_question(
            "Why did this engineering failure recur?",
            context={"is_incident": True},
        )
        self.assertEqual(route["mode"], "incident-analysis")

    def test_route_has_artifact(self):
        """Routed result should contain an initial artifact."""
        route = ds_lite_causal_router.route_causal_question(
            "Why does X cause Y?",
            context={"mechanism_known": True},
        )
        self.assertIn("artifact", route)
        self.assertEqual(route["artifact"]["schema"], "ds-lite.causal-model.v1")


class CausalModelTests(unittest.TestCase):
    def test_create_and_populate_model(self):
        """Should create a model, add nodes and edges."""
        model = ds_lite_causal_router.create_causal_model(
            "mechanism-chain",
            "Why does X improve Y?",
            ["Dataset D is available"],
        )
        ds_lite_causal_router.add_node(model, "n1", "X is present", "observed")
        ds_lite_causal_router.add_node(model, "n2", "Y improves", "hypothesis")
        edge = ds_lite_causal_router.add_edge(
            model, "n1", "n2", "causes", "AND", "hypothesis",
            evidence_refs=["ref1"],
            alternative_explanations=["Z could also cause Y"],
            falsifiers=["If X is removed, Y should not improve"],
        )
        self.assertEqual(len(model["nodes"]), 2)
        self.assertEqual(len(model["edges"]), 1)
        self.assertEqual(edge["relation"], "causes")

    def test_duplicate_node_rejected(self):
        """Duplicate node_id should be rejected."""
        model = ds_lite_causal_router.create_causal_model(
            "mechanism-chain", "Q", [],
        )
        ds_lite_causal_router.add_node(model, "n1", "Node 1", "observed")
        with self.assertRaises(ds_lite_causal_router.CausalRouterError):
            ds_lite_causal_router.add_node(model, "n1", "Duplicate", "observed")

    def test_edge_to_nonexistent_node_rejected(self):
        """Edge to nonexistent node should be rejected."""
        model = ds_lite_causal_router.create_causal_model(
            "mechanism-chain", "Q", [],
        )
        ds_lite_causal_router.add_node(model, "n1", "Node 1", "observed")
        with self.assertRaises(ds_lite_causal_router.CausalRouterError):
            ds_lite_causal_router.add_edge(model, "n1", "n2", "causes")


class CausalModelValidationTests(unittest.TestCase):
    def _make_valid_model(self):
        model = ds_lite_causal_router.create_causal_model(
            "mechanism-chain",
            "Why does X improve Y?",
            ["Dataset D is available"],
        )
        ds_lite_causal_router.add_node(model, "n1", "X is present", "observed")
        ds_lite_causal_router.add_node(model, "n2", "Y improves", "hypothesis")
        ds_lite_causal_router.add_edge(
            model, "n1", "n2", "causes", "AND", "hypothesis",
            evidence_refs=["ref1"],
            alternative_explanations=["Z could also cause Y"],
            falsifiers=["If X is removed, Y should not improve"],
        )
        return model

    def test_valid_model_passes(self):
        """A valid model should pass validation."""
        model = self._make_valid_model()
        result = ds_lite_causal_router.validate_causal_model(model)
        self.assertIn(result["verdict"], {"pass", "warning"})

    def test_single_root_cause_oversimplification_blocked(self):
        """Incident analysis with single edge should be blocked."""
        model = ds_lite_causal_router.create_causal_model(
            "incident-analysis", "Why did this fail?", [],
        )
        ds_lite_causal_router.add_node(model, "n1", "Failure", "observed")
        ds_lite_causal_router.add_node(model, "n2", "Root cause", "hypothesis")
        ds_lite_causal_router.add_edge(
            model, "n2", "n1", "causes", "UNKNOWN", "hypothesis",
            evidence_refs=["ref"],
            alternative_explanations=["Other causes"],
            falsifiers=["If root cause is fixed, failure should not recur"],
        )
        result = ds_lite_causal_router.validate_causal_model(model)
        self.assertEqual(result["verdict"], "blocked")
        self.assertIn("single_root_cause_oversimplification", result["rule_ids"])

    def test_model_digest_is_stable(self):
        """Model digest should be stable for the same model."""
        model1 = self._make_valid_model()
        model2 = self._make_valid_model()
        result1 = ds_lite_causal_router.validate_causal_model(model1)
        result2 = ds_lite_causal_router.validate_causal_model(model2)
        self.assertEqual(result1["model_digest"], result2["model_digest"])


if __name__ == "__main__":
    unittest.main()