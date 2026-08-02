import tempfile
import unittest
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
CONTROLLER_ROOT = ROOT / "plugins" / "deepscientist-lite-core" / "controller"
sys.path.insert(0, str(CONTROLLER_ROOT))

from ds_lite_control.domain import ControlStore, FenceRejected
from ds_lite_control.fake_app_server import FakeAppServer
from ds_lite_control.fault_harness import run_k1_k6


class ControlPlaneSpikeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="ds-lite-control-spike-"))
        self.store = ControlStore(self.root / "control.sqlite")

    def tearDown(self) -> None:
        self.store.close()

    def test_duplicate_action_has_one_logical_workflow_binding(self):
        first = self.store.plan_action("action-1", "turn")
        second = self.store.plan_action("action-1", "turn")
        self.assertEqual(first["workflow_id"], "action-1")
        self.assertEqual(second["workflow_id"], "action-1")
        self.assertEqual(self.store.workflow_binding_count("action-1"), 1)

    def test_stale_fence_cannot_mutate_action_or_outbox(self):
        self.store.plan_action("action-1", "turn")
        old = self.store.acquire_lease(
            "work-1", "owner-a", allow_unexpired_takeover=True
        )
        new = self.store.acquire_lease(
            "work-1", "owner-b", allow_unexpired_takeover=True
        )
        self.assertGreater(new, old)
        with self.assertRaises(FenceRejected):
            self.store.enqueue("action-1", old, "owner-a")
        self.store.enqueue("action-1", new, "owner-b")
        self.assertEqual(self.store.outbox_fence("action-1"), ("owner-b", new))

    def test_new_owner_persists_planned_outbox_takeover(self):
        self.store.plan_action("action-1", "turn")
        old = self.store.acquire_lease(
            "work-1", "owner-a", allow_unexpired_takeover=True
        )
        self.store.enqueue("action-1", old, "owner-a")
        new = self.store.acquire_lease(
            "work-1", "owner-b", allow_unexpired_takeover=True
        )
        self.store.enqueue("action-1", new, "owner-b")
        self.assertEqual(self.store.outbox_fence("action-1"), ("owner-b", new))

    def test_fake_host_never_starts_when_canonical_thread_is_missing(self):
        host = FakeAppServer()
        result = host.resume_or_classify("missing-thread")
        self.assertEqual(result["state"], "ambiguous")
        self.assertEqual(host.start_count, 0)

    def test_k1_to_k6_run_one_hundred_fixed_seed_trials_each(self):
        result = run_k1_k6(seed=20260731, trials=100)
        self.assertEqual(result["evidence_class"], "fake-host")
        self.assertEqual(set(result["cases"]), {"K1", "K2", "K3", "K4", "K5", "K6"})
        self.assertTrue(all(case["passed"] == 100 for case in result["cases"].values()))

    def test_runtime_dependency_and_attribution_are_pinned(self):
        lock = (CONTROLLER_ROOT / "requirements.lock").read_text(encoding="utf-8")
        sources = (CONTROLLER_ROOT / "third_party_sources.yml").read_text(encoding="utf-8")
        notices = (CONTROLLER_ROOT / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
        sbom = (CONTROLLER_ROOT / "sbom.spdx.json").read_text(encoding="utf-8")
        self.assertIn("dbos==2.29.0", lock)
        self.assertIn("dbos-transact-py", sources)
        self.assertIn("MIT", notices)
        self.assertIn('"SPDXID": "SPDXRef-DBOS"', sbom)


if __name__ == "__main__":
    unittest.main()
