# 上游项目清单与更新管理

当前登记的第三方来源位于 `plugins/deepscientist-lite/references/upstream-project-registry.json`。

| 项目 | 处置 | 当前来源 |
|---|---|---|
| nature-skills | adopted / adapted | Apache-2.0，固定 commit vendor，17 个 runtime skill |
| codex-autoresearch | adopted / adapted | MIT package 声明，固定 commit vendor，DS Lite bounded adapter |
| DeepScientist V2 | reference-only | 只保留概念和审计来源，不复制 AGPL 代码 |
| DeepScientist | reference-only | 只保留工作流 provenance |

## 使用命令

```text
python tools/validation/upstream_manager.py inventory --repo-root .
python tools/validation/upstream_manager.py verify --repo-root .
python tools/validation/upstream_manager.py check --repo-root . --output <fresh-report.json>
python tools/validation/upstream_manager.py diff --repo-root . --output <fresh-report.json>
python tools/validation/upstream_manager.py plan-update --repo-root . --output <fresh-plan.md>
```

检查只读取远端 commit、许可证和来源结构，遇到网络失败记录 `not-observed`。它不会覆盖 vendor、自动合并、自动发布或修改正式配置。每周 GitHub Actions 只生成脱敏审计 artifact；人工审阅并完成适配测试后，才允许更新固定快照。
