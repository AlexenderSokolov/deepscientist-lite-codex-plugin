#!/usr/bin/env python3
"""Rewrite the two upstream adoption documents with the current authorization facts."""

from pathlib import Path


AUDIT = """# codex-autoresearch 集成审计

## 上游与授权

| 项目 | 记录 |
|---|---|
| 仓库 | https://github.com/congwa/codex-autoresearch |
| 固定 commit | `f2389bffbb4cd7789deb6796bc4ba35bf31f2a90` |
| npm 版本 | `0.1.5-beta.0` |
| 许可证证据 | `package.json` 声明 MIT；根目录许可证文件仍需继续核对 |
| 使用授权 | 作者已明确允许自由选用、修改和集成 |
| 当前处置 | `adopted / adapted` |
| 是否复制源码 | `yes`，仅复制已获授权的固定快照，保留来源和许可证说明 |
| vendor 路径 | `plugins/deepscientist-lite/vendor/codex-autoresearch/f2389bffbb4cd7789deb6796bc4ba35bf31f2a90` |

## 保留与适配

| 上游组件 | 处置 | DeepScientist Lite 适配 |
|---|---|---|
| README/workflow | adapted | 映射为 DS Lite 的 bounded continuation 与交接协议 |
| completion protocol | adapted | 增加冻结目标、证据门、acceptance gate 和失败冻结 |
| job loop | adapted | 前台、有界轮次、零自动重试、超时终止 |
| planning/policy/state | adapted | 显式 workdir、state-dir、sandbox、approval 和脱敏 receipt |
| Codex engine | adapted | 固定 CLI、argv 传递、子进程/管道状态归约 |
| CLI/package | adopted/adapted | 保存来源源码并接入 `fake`、`native-codex`、`codex-autoresearch` adapter |
| shell wrapper | adapted | 只保留 ASCII 参数编排，不嵌入 Python 或多行源码 |
| TypeScript tests | adopted as source evidence | 不直接替代 DS Lite unittest，另写边界测试 |

保留的核心能力：冻结目标、完成信号、会话 continuation、状态模型、计划和结果对账。

## 明确拒绝的默认行为

不采用无限循环、隐式 retry、daemon、queue、后台 scheduler、自动 tmux、默认高权限、原始日志、绝对路径、自动外发和静默全局配置修改。原因是这些行为会破坏 DS Lite 的可审计性、隐私边界或重复风险控制。

## 追踪矩阵

| 上游概念 | DS Lite 实现 | 证据 |
|---|---|---|
| frozen goals | `ds-lite.loop-contract.v1` | `tests/test_loop_runner.py` |
| completion gate | evidence gate + summary verify | completion-without-evidence 测试 |
| bounded continuation | `plugins/deepscientist-lite/scripts/ds_lite_loop.py` | fake partial-to-completed 测试 |
| fail-closed stop | 固定 failure class 和 acceptance gate | ambiguous/timeout/duplicate-risk 测试 |
| source provenance | vendor snapshot + audit table | `tools/validation/upstream_manager.py verify` |
| secret-safe state | 脱敏 receipt | secret marker exclusion 测试 |

## 当前状态

离线 Loop acceptance 已通过；真实 provider、完整 Hook、真实 child-agent delegation、matched effect、formal cache、fresh Desktop 和 release gate 仍未验证。离线结果不能解锁真实门。
"""

EMAIL = """# 给 codex-autoresearch 作者的邮件草稿

**主题：感谢 codex-autoresearch，并咨询自由采用与署名方式**

您好：

感谢您公开 codex-autoresearch。它解决了 Codex 长任务容易提前停止、需要人工反复提醒的问题，对我们很有启发。

我们维护一个叫 **DeepScientist Lite** 的 Codex 插件，用来帮助科研和工程项目保留目标、安排后续步骤、检查证据，并在真正完成前避免过早结束。我们希望把 codex-autoresearch 的长任务思路完整整合进去，并根据自己的安全边界做适配：限制执行轮次、保留完成证据、遇到不确定或危险情况就停止。

我们目前参考并保存的是 commit `f2389bffbb4cd7789deb6796bc4ba35bf31f2a90`、npm `0.1.5-beta.0`。`package.json` 中声明了 MIT；如果这确实代表项目的正式授权，我们希望在项目中自由修改、采用和再分发适配后的版本，并保留来源说明。

想请教您三件事：

1. 是否可以确认我们可以自由修改、采用和集成这套代码？
2. 您是否愿意在仓库根目录补充正式的 `LICENSE` 文件？
3. 您偏好的署名、项目链接或致谢方式是什么？

我们会保留上游来源和改动说明，也欢迎您审阅我们的适配方式并提出建议。

再次感谢您的工作！

祝好

DeepScientist Lite 维护者
"""

AUTORESEARCH_TEST = '''from __future__ import annotations

import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class AutoresearchAuditTests(unittest.TestCase):
    def test_external_adapter_is_documented_as_bounded_and_blocked_until_authorized(self) -> None:
        protocol = (REPO_ROOT / "plugins" / "deepscientist-lite" / "references" / "bounded-loop-protocol.md").read_text(encoding="utf-8")
        audit = (REPO_ROOT / "docs" / "maintainers" / "codex-autoresearch-integration-audit.zh.md").read_text(encoding="utf-8")
        combined = protocol + "\\n" + audit
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
'''


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    (root / "docs" / "maintainers" / "codex-autoresearch-integration-audit.zh.md").write_text(AUDIT, encoding="utf-8", newline="\n")
    (root / "docs" / "maintainers" / "email-to-codex-autoresearch-author.zh.md").write_text(EMAIL, encoding="utf-8", newline="\n")
    (root / "tests" / "test_autoresearch_audit.py").write_text(AUTORESEARCH_TEST, encoding="utf-8", newline="\n")
    print("rewrote upstream adoption documents")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
