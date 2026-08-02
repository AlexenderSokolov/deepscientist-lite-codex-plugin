# DS Lite 控制面 Phase 3 实施状态

最后更新：2026-07-31

## 当前阶段

Phase 3 已通过。权威收据为
`research/.validation-tmp/control-plane-phase3-final-20260731-03/phase3-decision.json`，
SHA-256 为 `6fba9ca1417efa3a36faecf45d852b902ddc8a57481dfacc50be112b143a1341`。
它记录 `phase3_decision=go`、`phase4_goal_allowed=true`，同时继续保持
`release_allowed=false`。

## 最终真实宿主观察

- 先前的 provider 超时归因仅适用于强制隔离 `CODEX_HOME` 的旧实验；它不是当前 provider 可用性的结论。
- 最终 smoke 明确选择 `ambient-home`：不读取、复制、显示或修改凭据，仅移除继承的 `CODEX_HOME` 覆盖，使子进程解析用户已有的正常 Codex 会话。该模式是显式 opt-in，绝非默认行为。
- 在 Codex `0.146.0-alpha.3.1`、Python `3.13.5`、DBOS `2.29.0`、模型 `gpt-5.6-sol` 下，真实 app-server 多 gate smoke 通过：一个 app-server、两个独立 canonical thread、恰好两次 `turn/start`、一次真实响应丢弃后调和、三代 controller 的 TTL fence 接管、一次工具副作用以及两个 terminal gate。
- 运行器重跑 K10/K11 各 100 次、supervised recovery、Windows 资源探针、101 项阶段测试、7 项支持测试和 Core validation，全部通过。协议 journal 有效，`release_allowed=false`。

## 已实现并观察

- domain schema v3、显式 v2→v3 migration、DAG ready/claim、默认并发 2 和 retry 并发 1。
- 统一 failure classifier：cooldown、awaiting-user、ambiguous reconciliation、valid negative 和连续签名 circuit。
- gate 局部失败不改变无依赖 gate 的 ready/running 状态；cooldown 使用版本化 DBOS workflow。
- lease TTL 到期后的 running action 可由新 owner/fence 接管，保留原 attempt/action/workflow identity；旧 fence mutation 被拒绝。
- 每 gate 独立 canonical thread，context handoff 只允许一个显式 successor。
- 仓库内前台 supervisor、heartbeat/status truth、review-only Windows/systemd 模板和 backup v4。
- K10 与 K11 固定种子 `20260731` 各 100 次通过。K10 是 SQLite fencing 外部进程证据，K11 是真实 DBOS 2.29.0 SQLite 外部进程恢复证据；最近一次可复核矩阵为
  `research/.validation-tmp/control-plane-phase3-offline-20260731-03/fault-matrix.json`。
- supervised probe 实际终止第一代 controller，由第二代恢复同一 action、递增 fence，并使两个 gate 收敛 terminal；随后完成 control DB、DBOS DB、receipts、broker journal 和 supervisor witness 的新目录恢复：
  `research/.validation-tmp/control-plane-phase3-offline-20260731-03/supervised-recovery.json`。
- Windows 资源探针使用系统 `Get-Process` 记录启动、RSS/CPU 和控制数据增长，不新增第三方依赖：
  `research/.validation-tmp/control-plane-phase3-offline-20260731-03/resource-windows.json`。

## 已保留的历史诊断与阶段外风险

- 隔离 `CODEX_HOME` 下的 `request timed out` 以及 `control-plane-phase3-real-20260731-07/` 均保留为历史失败证据；它们说明该隔离路径不具备可用会话，不能覆盖最终的 ambient-home 实验，也不能被删除或重写。
- PowerShell runner 已通过 parser 检查，Bash runner 已用 Git Bash 通过 `bash -n`；非 Windows 实际执行仍属于 Phase 5 平台验收。
- 非 Windows 资源、Phase 4 的独立 reviewer/release aggregate 和 Phase 5 跨平台发布验收都不属于本阶段完成证据。尤其是 `release_allowed=false`，不得从 Phase 3 go 推断发布许可。

## 下一阶段边界

1. 可以建立独立的 Phase 4 goal，用确定性 verifier、独立 reviewer 和严格 release aggregate 覆盖科学 gate 与发布真值。
2. Phase 4 不得修改 Phase 3 receipt，不得将历史超时改写为成功，也不得把 Phase 3 的真实 Codex 证据推断为 release 许可。
3. Phase 5 保留给非 Windows 平台和跨平台真实宿主混沌验收。
