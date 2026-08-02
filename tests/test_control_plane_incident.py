import tempfile
import unittest
from pathlib import Path

from teaching.control_plane_incident import record_false_success_incident, record_receipt_write_incident


class ControlPlaneIncidentTests(unittest.TestCase):
    def test_receipt_write_incident_is_redacted_and_write_once(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            destination = root / "incident.json"
            receipt = record_receipt_write_incident(
                destination,
                attempted_receipt_id="canonical-thread-smoke-05",
                target_path=root / "blocked" / "receipt.json",
                stage="receipt-write",
            )
            self.assertEqual(receipt["failure_layer"], "evidence/receipt-write")
            self.assertFalse(receipt["raw_command_persisted"])
            self.assertFalse(receipt["raw_output_persisted"])
            self.assertNotIn("canonical-thread-smoke-05", destination.read_text(encoding="utf-8"))
            with self.assertRaises(FileExistsError):
                record_receipt_write_incident(
                    destination,
                    attempted_receipt_id="canonical-thread-smoke-05",
                    target_path=root / "blocked" / "receipt.json",
                    stage="receipt-write",
                )

    def test_rejects_unrecognized_incident_stage(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                record_receipt_write_incident(
                    Path(directory) / "incident.json",
                    attempted_receipt_id="identity",
                    target_path=Path(directory) / "receipt.json",
                    stage="unknown",
                )

    def test_false_success_receipt_is_quarantined_without_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            receipt = record_false_success_incident(
                Path(directory) / "incident.json",
                source_receipt_id="dbos-sqlite-recovery-02",
                source_receipt_sha256="a" * 64,
                reason="outbox-fence-persistence-not-verified",
            )
            self.assertTrue(receipt["source_receipt_quarantined"])
            self.assertFalse(receipt["source_receipt_overwritten"])


if __name__ == "__main__":
    unittest.main()
