# DS Lite 控制面 Phase 4 实施状态

最后更新：2026-08-01

## 当前阶段

Phase 4 已通过。权威 write-once 收据为
`research/.validation-tmp/control-plane-phase4-final-20260801-10/phase4-decision.json`，
SHA-256 为
`83e32bb80a20989161412fc83ff85736f85ab7b8c50479da046cb7b7dc611f5a`。
它记录 `phase4_decision=go`、`phase5_goal_allowed=true`，同时继续保持
`release_allowed=false`。

Phase 3 权威收据保持不变：
`research/.validation-tmp/control-plane-phase3-final-20260731-03/phase3-decision.json`，
SHA-256 为
`6fba9ca1417efa3a36faecf45d852b902ddc8a57481dfacc50be112b143a1341`。

## 已实现

- domain schema v4 与显式 v3→v4 migration；未知版本与 downgrade 均 fail closed。
- `evidence_sets`、`evidence_members`、`verifier_runs`、`review_requests`、
  `review_results`、`gate_decisions`、`release_profiles`、`release_decisions`、
  `private_witness_index` 和 `integrity_incidents` 的 fenced domain truth。
- canonical evidence manifest、路径/类型/大小/hash 检查、敏感字段拒绝和隔离 private spool。
- 版本化确定性 verifier、独立 reviewer sidecar、严格 gate decision 与 release aggregate。
  worker/model 的 `passed`、`gate_passed` 和 `release_allowed` 字段不参与判定。
- `ds-lite.project-status.v3` 为 gate/release 结论附带 domain 或 write-once receipt 来源；
  receipt/index/hash 缺失或冲突时 fail closed。
- backup v5 纳入 control DB、DBOS DB、receipts、protocol journal、supervisor witness、
  evidence manifest、private spool hash 和 release decision；恢复只写入新目录。
- `formal_release_gate.py` 保留 v1/v2 行为，v3 通过共享严格聚合内核，不自动升级旧收据。

## 已观察证据

- `research/.validation-tmp/control-plane-phase4-final-20260801-10/real-reviewer-smoke.json`
  记录真实 Codex `0.146.0-alpha.3.1`、模型 `gpt-5.6-sol`、schema digest
  `0e79541ba5af824864df3bd14c35ea2678009bce1a6864a3ce6213d9f0228509`。
  reviewer 与 worker thread 不同；reviewer 和独立 canary 均由 wire journal 证明
  `sandbox=read-only`、`approvalPolicy=never`。canary 写命令被宿主拒绝，artifact digest
  前后不变，正式 sidecar terminal，receipt 不含模型原文。
- `reviewer-fault-matrix.json` 使用固定 seed `20260801`，在 verifier receipt 写入后、
  reviewer terminal 后、sidecar 写入后和 aggregate receipt 写入后四个切点各运行
  100 次；全部保持 receipt 字节、补齐索引、幂等重放并拒绝旧 fence。
- `status-traceability-02.json` 证明所有结论可追溯，managed doctor 的 Python、DBOS、
  schema、domain integrity、protocol/broker journal 检查均通过。
- `backup-recovery.json` 证明 backup v5 新目录恢复和 hash 校验通过。
- 当前项目 aggregate 诚实保持 blocked，唯一缺失 gate 为 `phase5-real-host`，
  `release_allowed=false`。
- Phase 0–4 控制面回归为 126/126，支持测试 11/11，Core validation 通过。

## 证据边界

- reviewer 是真实 Codex 宿主证据；确定性 verifier matrix 与四类故障矩阵分别是
  offline 和 SQLite/filesystem external-process 证据，不能冒充真实提供商故障。
- 显式 `ambient-home` 仅复用用户已有 Codex 会话解析，不读取、复制、显示或修改凭据，
  也不修改全局 trust。Windows 沙箱内的 socket 10013 是受限网络路径失败，不是 provider
  不可用；获准的真实 smoke 已完成。
- Phase 4 不证明非 Windows 平台、跨平台真实宿主混沌或项目 release readiness。

## 下一阶段边界

1. 可以建立独立 Phase 5 goal，执行非 Windows 平台、跨平台真实宿主混沌和完整发布
   profile 验收。
2. Phase 5 不得修改 Phase 4 收据，也不得把 `phase5_goal_allowed=true` 解读为发布许可。
3. 项目 release aggregate 当前仍因缺少 `phase5-real-host` gate 而 blocked，
   `release_allowed=false`。
