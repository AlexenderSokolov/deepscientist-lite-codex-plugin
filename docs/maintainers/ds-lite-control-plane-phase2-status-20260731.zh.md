# DS Lite 控制面 Phase 2 实施状态

最后更新：2026-07-31

## 当前阶段

Phase 2 continuation：实现与证据 gate 已完成，当前正式结论为 **go**。Phase 1 decision
`research/.validation-tmp/control-plane-phase1-20260731-03/phase1-decision.json`
的 SHA-256 为
`4fbb142f5cc7b46b5619f93705dede9642004b4208bcf7cec6d1db313e76af2b`。

## 已完成

- domain schema v1 -> v2 显式 migration；新增 canonical thread lifecycle、fenced RPC request 和 append-only protocol journal。
- controller-owned schema-bound app-server transport；支持并发 waiter、notification 早到、response loss、畸形 JSON、进程退出和 `active/terminal/ambiguous` 分类。
- `CodexActionRunner` 固定 `action_id:turn-start` request identity；response loss 不重发，旧 fence 在 host 写入前拒绝。
- 新增 `run_codex_action_v1`，保留 Phase 1 `run_action_v1` 语义不变。
- K4-K7/K12 外部进程 fake-host harness 固定种子各 100/100 通过。
- 89 项 Phase 0.5/1/2 回归和 Core package validation 通过。
- controller-owned 真实 app-server 在同一 canonical thread 上完成三个 terminal turn，并观察 start/list/read/archive/unarchive/resume。
- `research/.validation-tmp/control-plane-phase2-20260731-03/phase2-decision-02.json` 为 write-once no-go，SHA-256 `9e3187a2f16e922a6e6360000c914dfabbb57e38695250de9c5be3a5a085372b`。
- 新增仅绑定 `127.0.0.1` 随机端口的 token-authenticated fault broker；broker 独占真实 app-server、维护 fsync/hash-chain wire journal，并允许 controller worker 断开后重连。
- 固定 Codex `0.128.0` 的真实实验观察到一个 app-server PID、一个 canonical thread、四个 controller PID、恰好三次 `turn/start`。第三个真实 response 被丢弃后，新 controller 接回同一 terminal turn，没有重发。
- pending archive 的真实 response 被丢弃后，新 controller 通过 active/archived 精确列表调和为唯一 archived，`thread/archive` 只发送一次。
- broker-aware backup v3 包含 domain DB、DBOS DB、receipts、protocol journal 和不含 token 的 metadata；缺项或 hash 不符时 fail closed。
- `research/.validation-tmp/control-plane-phase2-continuation-20260731-06/phase2-decision-03.json` 为当前权威 write-once go，SHA-256 `9b867e230f4edcafd35750fc0b0fd115da642b8cb86ae649aa83b4e2ed66eb4e`。
- doctor 现场计算固定 schema 的 `SHA256SUMS` 摘要；已修复旧常量少一个 `f` 且把期望值当观察值的错误成功路径。

## 当前阻塞层

Phase 2 核心阻塞已经解除。失败 identity 全部保留：`-01` 暴露 terminal notification 晚到窗口，`-03/-04` 暴露 PowerShell stderr/warning 捕获问题，`-05` 初次 decision assembly 暴露旧 smoke 路径错误；这些失败均未覆盖，最终 decision 只引用实际通过的 artifact hash。

## 下一可自动执行动作

允许建立独立 Phase 3 goal，实施多 gate DAG 调度、局部失败隔离与 cooldown；不得在 Phase 3 开始 reviewer/release aggregate，也不得把 broker 当作系统服务或 supervisor。

## 尚未观察

- 非 Windows 平台资源验收；
- Phase 3 scheduler、Phase 4 reviewer/release、Phase 5 混沌发布验收。

`phase3_goal_allowed=true`，`release_allowed=false`。
