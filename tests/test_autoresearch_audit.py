from __future__ import annotations

import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class AutoresearchAuditTests(unittest.TestCase):
    def test_external_adapter_is_documented_as_bounded_and_blocked_until_authorized(self) -> None:
        protocol = (REPO_ROOT / "plugins" / "deepscientist-lite" / "references" / "bounded-loop-protocol.md").read_text(encoding="utf-8")
        audit = (REPO_ROOT / "docs" / "maintainers" / "codex-autoresearch-integration-audit.zh.md").read_text(encoding="utf-8")
        combined = protocol + "\n" + audit
        for anchor in ("blocked-not-verified", "external-policy-unverified", "bounded", "does not execute"):
            with self.subTest(anchor=anchor):
                self.assertIn(anchor, combined)

    def test_audit_preserves_authorized_vendor_provenance(self) -> None:
        audit = (REPO_ROOT / "docs" / "maintainers" / "codex-autoresearch-integration-audit.zh.md").read_text(encoding="utf-8")
        for anchor in (
            "f2389bffbb4cd7789deb6796bc4ba35bf31f2a90",
            "0.1.5-beta.0",
            "package.json",
            "adopted / adapted",
            "`yes`",
            "vendor",
            "冻结目标",
            "bounded continuation",
        ):
            with self.subTest(anchor=anchor):
                self.assertIn(anchor, audit)

    def test_email_is_short_and_does_not_leak_internal_runtime_details(self) -> None:
        email = (REPO_ROOT / "docs" / "maintainers" / "email-to-codex-autoresearch-author.zh.md").read_text(encoding="utf-8")
        self.assertIn("MIT", email)
        self.assertIn("自由修改", email)
        self.assertIn("DeepScientist Lite", email)
        self.assertNotIn("raw JSONL", email)


if __name__ == "__main__":
    unittest.main()
