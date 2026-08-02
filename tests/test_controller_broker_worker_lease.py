from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ds_lite_control.store import ControlStore
from teaching.controller_broker_worker import take_over_expired_lease


class ControllerBrokerWorkerLeaseTests(unittest.TestCase):
    def test_recovery_waits_for_expiry_then_uses_new_owner_and_epoch(self) -> None:
        now = [datetime(2026, 7, 31, tzinfo=timezone.utc)]
        with tempfile.TemporaryDirectory() as temp:
            store = ControlStore(Path(temp) / "control.sqlite3", clock=lambda: now[0])
            try:
                first_epoch = store.create_job_work_item(
                    "job", "work", "owner-a", lease_ttl_seconds=5,
                )

                def advance(_: float) -> None:
                    now[0] += timedelta(seconds=6)

                next_epoch = take_over_expired_lease(
                    store, "work", "owner-b", timeout=1, wait=advance,
                )
                self.assertEqual(first_epoch, 1)
                self.assertEqual(next_epoch, 2)
            finally:
                store.close()


if __name__ == "__main__":
    unittest.main()
