from __future__ import annotations

import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_ROOT = REPO_ROOT / "plugins" / "deepscientist-lite"
UPSTREAM_URL = "https://github.com/WENGSYX/DeepScientist_V2/releases/tag/v2.1.8"
UPSTREAM_COMMIT = "49ffdcda6ce159505f6119b1e26d79c8503a8286"
UPSTREAM_SKILL_BLOB = "6f58083e8f0a951a0773d94f5b0812484febc8c3"


class UpstreamTransferTests(unittest.TestCase):
    def test_notice_pins_upstream_and_agpl_isolation_boundary(self) -> None:
        notice = (REPO_ROOT / "NOTICE").read_text(encoding="utf-8")
        for anchor in (
            UPSTREAM_URL,
            UPSTREAM_COMMIT,
            UPSTREAM_SKILL_BLOB,
            "AGPL-3.0-only",
            "does not copy upstream code, schemas, or skill text",
        ):
            with self.subTest(anchor=anchor):
                self.assertIn(anchor, notice)

    def test_transfer_audit_maps_invariants_and_rejects_finance_residue(self) -> None:
        audit_path = (
            REPO_ROOT
            / "docs"
            / "maintainers"
            / "deepscientist-v2.1.8-factor-transfer-audit.zh.md"
        )
        if not audit_path.is_file():
            self.skipTest("maintainer docs are private (gitignored)")
        audit = audit_path.read_text(encoding="utf-8")
        for anchor in (
            UPSTREAM_URL,
            UPSTREAM_COMMIT,
            UPSTREAM_SKILL_BLOB,
            "未测量指标",
            "真实 checks",
            "外部 pending/submit",
            "唯一写入入口",
            "legacy",
            "单轴 ablation",
            "Finance residue",
            "reject",
            "factor_registry",
            "continuous mode",
        ):
            with self.subTest(anchor=anchor):
                self.assertIn(anchor, audit)

    def test_factor_card_guidance_preserves_unknown_checks_and_failed_probes(self) -> None:
        protocol = (
            PLUGIN_ROOT / "references" / "scientific-factor-card-protocol.md"
        ).read_text(encoding="utf-8")
        idea = (PLUGIN_ROOT / "skills" / "ds-lite-idea" / "SKILL.md").read_text(
            encoding="utf-8"
        )
        review = (PLUGIN_ROOT / "skills" / "ds-lite-review" / "SKILL.md").read_text(
            encoding="utf-8"
        )
        for text in (protocol, idea, review):
            for anchor in (
                "unmeasured",
                "real checks",
                "decision reason",
                "single-axis ablation",
                "failed checks",
            ):
                with self.subTest(document=text[:40], anchor=anchor):
                    self.assertIn(anchor, text)

    def test_core_runtime_and_templates_contain_no_finance_execution_contract(self) -> None:
        paths = sorted((PLUGIN_ROOT / "scripts").glob("*.py"))
        paths.extend(sorted((PLUGIN_ROOT / "assets" / "templates").rglob("*")))
        text = "\n".join(
            path.read_text(encoding="utf-8", errors="strict").lower()
            for path in paths
            if path.is_file()
        )
        for forbidden in (
            "worldquant",
            "wq brain",
            "qlib",
            "factor_registry",
            "submit_qualified",
            "self_correlation",
            "stock_pool",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, text)


if __name__ == "__main__":
    unittest.main()
