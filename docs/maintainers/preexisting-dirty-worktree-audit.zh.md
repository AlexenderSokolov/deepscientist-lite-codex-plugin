# 原工作区脏改动分类审计

> 观察时间：2026-07-18。本文是路径级隔离记录，不是对原工作区 66 个改动的功能验收。

## 工作区边界

| 项目 | 原工作区 | 本计划独立 worktree |
| --- | --- | --- |
| 路径 | `D:/Study_Works/WestLakeNLP/deepscientist-lite-codex-plugin` | `D:/Study_Works/WestLakeNLP/deepscientist-lite-codex-plugin-v0.5-communication` |
| 分支 | `codex/v0.5-factor-workspace` | `codex/v0.5-communication-seven` |
| 观察到的 HEAD | `83e2e3f` | 基线 `992c53e`，其上为未提交实现 |
| 状态 | 45 个已跟踪修改，21 个未跟踪路径 | 只承载 0.5.0-beta.2 沟通审计计划 |

原工作区没有被 reset、checkout 覆盖、删除或批量清理。本 worktree 从较早的干净提交重新实现沟通层；路径重叠不表示合并了原工作区的脏字节。

## 分类表

| 类别 | 原工作区路径或范围 | 本 worktree 处理 | 理由 |
| --- | --- | --- | --- |
| 选择性化用：hook 事件与安全边界 | `plugins/deepscientist-lite/hooks/hooks.json`、`plugins/deepscientist-lite/scripts/ds_lite_hook.py`、`tests/test_hooks.py` | 保留四事件名称和“不在 manifest 注册”的边界；重新实现为通信审计 gate，并增加用户确认、宿主格式未知时 `host_supported: false`、完成声明、递归删除、破坏性 Git、显式提权和一次补救检查 | 与本计划直接相关，但原草稿没有 `communication-audit.v1`，不能整体复制 |
| 选择性化用：迭代反思与用户汇报 | `plugins/deepscientist-lite/scripts/ds_lite_iteration.py`、`tests/test_iteration.py` | 只在 Stop 中检查 active iteration 的 `reflection` 与 `user_report` 是否缺失 | 本计划要求反思和汇报硬门；不引入完整 iteration schema、CLI 或新状态字段 |
| 明确不移植：第八 skill 与协调入口 | `plugins/deepscientist-lite/skills/ds-lite-coordinate/`、`plugins/deepscientist-lite/skills/ds-lite/` 及相关 agent metadata | 未移植 | 本计划固定为七个 skill，不新增第八个 skill，也不引入外部 Agent 编排入口 |
| 明确不移植：Factor Card 与探索契约扩展 | `references/scientific-factor-card-protocol.md`、`references/responsible-exploration-covenant.md`、`references/skill-trigger-matrix.json`、`tests/test_skill_triggers.py`、`tests/test_upstream_transfer.py` | 未移植 | 属于另一条 Factor/trigger/transfer 研究线，不是沟通层的必要依赖 |
| 明确不移植：教学与 pilot | `teaching/` 下 matched-control、action-reflection、canary/pilot、runner、评分与课程改动，以及 `tests/test_teaching_labs.py`、`tests/test_pilot_runtime.py` | 未移植 | 教学实验是独立工作流；本计划只生成非运行时 12 案例 A/B fixture |
| 明确不移植：反思哲学与上游迁移报告 | `docs/maintainers/action-reflection-philosophy.zh.md`、`docs/maintainers/deepscientist-v2.1.8-factor-transfer-audit.zh.md` | 未移植 | 只保留与通信计划直接相关的方法论反思边界，不导入另一版本的设计结论 |
| 重叠路径，独立重做 | 根 README/NOTICE/PACKAGE/PROJECT、实现与发布文档、manifest、`ds_lite_state.py`、七个既有 skill、acceptance/validation 脚本和测试 | 从 `992c53e` 基线按本计划逐项编辑，没有套用原工作区 diff | 这些路径同时被两条开发线修改；直接合并会混入第八 skill、教学 pilot 或未验收 schema |
| 保持原状 | 原工作区其余所有已跟踪与未跟踪路径 | 未写入、未删除、未暂存 | 遵守脏工作区保护和分步迭代原则 |

## 可复核命令

```powershell
git -C D:\Study_Works\WestLakeNLP\deepscientist-lite-codex-plugin status --short --branch
git -C D:\Study_Works\WestLakeNLP\deepscientist-lite-codex-plugin diff --name-status
git -C D:\Study_Works\WestLakeNLP\deepscientist-lite-codex-plugin-v0.5-communication status --short --branch
```

这份表只证明隔离与选择范围。原工作区中的 Factor Card、教学、coordinate、hook 或 iteration 草稿是否正确，仍需在其所属分支独立审查。
