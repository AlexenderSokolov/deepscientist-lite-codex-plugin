# DeepScientist Lite 路线图与延期门

本文只记录会影响后续实现和发布判断的长期事项。临时命令、单次失败和执行流水账不写入这里。

## 当前发布线

`v0.4.0-beta.2` 发布 P0 的 work unit、typed evidence/review、Mission Board 和单轮 worker handoff。Graph v2、Evidence Pack v1、旧 CLI 与字符串 `next_action` 保持兼容。该版本可以作为 source/package prerelease 使用，但 fresh cache installation 和新线程发现仍未验证。

## 下一条短期线

- 领域中立 Factor Card：源码已实现 schema、validator、模板及 idea/review 规则；fresh-agent 行为仍待授权验收，不做自动加权真值或金融 DSL。
- 有界任务协调：源码已实现 `ds-lite.delegation.v1`、`$ds-lite-coordinate`、最多三个明确授权子任务、路径所有权、预算、回传和集成责任；真实子智能体 forward test 尚未授权，不提供 daemon、队列或后台 scheduler。
- 真实教学 pilot：静态基础设施已实现，可确定性准备 matched plain、scratchpad 和 DS Lite 三组、四案例共 12 个 pending workspace，并生成分轮提示、输入摘要、评分表和学生/教师指南。真实 Codex 运行、成本记录和盲评尚未授权；当前没有效果结论。

只有 12-arm 真实产物完成脱敏、统一评分并通过复核后，才讨论 `0.5.0-beta.1` 候选。单次 pilot 只提供描述性证据，不验证保留 profile，也不构成统计显著性结论。

## 延期 P1-P3

| 门 | 延期接口 | 当前可用替代 | 发布声明 |
| --- | --- | --- | --- |
| P1 | action envelope、iteration receipt、idempotency/stale-revision transaction | `$ds-lite-iterate` skill 的单轮停止规则 | 未实现 |
| P2 | typed external-long profile、failure/retry/resource helper | `external-task-*` / `external-tmux-plan-*` Markdown handoff | provisional |
| P3 | cache/new-thread、真实 tmux/provider、macOS、完整跨模式矩阵 | source/package validation 与待验收清单 | not verified |

延期项不得阻塞普通 none/inline 项目的使用，但不得被默认值、示例或宣传写成已经支持。只有真实案例、可确定验证和兼容测试齐全后，才重新经过 core/profile/fixture/reject 审计。

## 长期不做

Lite 不增加 daemon、后台 scheduler、队列、MCP、Web/TUI、connector、模型路由、数据库或无限自动循环。外部长任务由稳定外部 owner 管理；Lite 只保存有界任务、证据、review、交接和停止理由。
