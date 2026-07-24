# Loop 工程真实链路验收（2026-07-23）

## 目标

在离线 Loop、transport、Hook、delegation、matched 和跨系统门通过后，
按 fresh-only 顺序验证真实 Codex/provider wire、CLI、Hook host、真实子智能体、
matched effect、formal cache 与 fresh host。正式发布门始终保持未发布。

## 授权与边界

- 用户已在当前任务中明确授权复用现有环境 API key 并继续真实实验。
- 每个真实假设使用新的身份和新的 F/G 根目录；每个请求最多一次。
- 不读取、重放或改写 `communication-beta2-20260720-gated-02`。
- 不保存凭据、URL、prompt、raw JSONL、stdout/stderr、隐藏推理、环境变量或工作站绝对根目录。
- timeout、auth、rate-limit、network、protocol、ambiguous 与 duplicate-risk 立即冻结。
- 不删除文件，不修改正式 credential/global config，不创建 daemon、queue、scheduler、数据库、MCP 或自动 tmux。
- formal cache、fresh Desktop 与 release 只能在所有前置门通过后执行；任何真实门失败时停止其依赖门。

## 当前状态

状态：`authorized / wire-passed / cli-canary-passed / trusted-hook-partial / downstream-frozen`。

离线统一验收已通过；真实结论只能在命令实际执行后追加，不能由 fake 或源码测试推断。

## 2026-07-23 实际观察

本轮真实诊断严格使用 fresh-only 身份，每个身份只发起一次 provider 请求：

| 身份 | 唯一变化 | 观察 | 结论 |
|---|---|---|---|
| `communication-beta2-20260723-loop-wire-02` | baseline | HTTP 400/4xx，连接和响应头到达，terminal=false，usage=0 | `protocol / frozen` |
| `communication-beta2-20260723-loop-wire-03` | 仅增加 Responses Lite header | HTTP 400/4xx，其余终态相同 | `protocol / frozen` |
| `communication-beta2-20260723-loop-wire-04` | 保留 header，input 改为 Codex `message[]` | HTTP 502/5xx，其余终态相同 | `protocol / frozen` |

所有 receipt 均只保存脱敏状态、request-id hash、请求次数和相对 evidence 引用；不保存原始 response、error message、URL、prompt、认证值或完整 JSONL。后续 `loop-wire-05` 已达到 `2xx + terminal + non-zero usage`，`gated-cli-01` 的 pinned CLI canary 也通过。`trusted-hook-05` 只提供 partial loader evidence，完整 Hook gate 仍 blocked。离线 Loop receipt `.validation-tmp/offline-loop-acceptance-20260723-final/offline-loop-acceptance.json` 证明 fake continuation 和 external adapter fail-closed，但不解锁真实 delegation、matched effect、formal cache、Desktop 或 release。
