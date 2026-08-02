# DS Lite 控制面 Phase 1 实施状态

最后更新：2026-07-31

## 当前阶段

Phase 1：混合控制器基础完成。最新 write-once decision 为 **go（仅允许建立独立 Phase 2 goal）**；`release_allowed=false`。

## 已由代码和测试证实

- Domain SQLite 使用版本化 schema、WAL、`synchronous=FULL`、foreign keys、`BEGIN IMMEDIATE` 和 fail-closed migration；不推测迁移 Phase 0.5 无版本 spike 数据库。
- `action_id` 对相同 payload 幂等，对冲突 payload 触发 integrity incident；DBOS bridge 固定 `workflow_id=action_id`。
- lease/fencing 绑定明确 work item resource；旧 owner/epoch 不能更新 outbox、workflow binding、host event 或 receipt index。
- terminal outbox 不可重新打开；duplicate submission 对 terminal action 只 retrieve 既有 workflow。
- receipt 使用 canonical JSON、exclusive create、文件 fsync 和独立 receipt index；K8 可从 terminal event 重建，K9 可补 index 且不同内容拒绝覆盖。
- managed CLI 提供 `doctor`、`control run/status/backup/restore`；默认 Python 3.14.4 不允许 managed，固定 Python 3.13.5/DBOS 2.29.0 才允许。

## 当前证据

- Phase 0.5 基线：`research/.validation-tmp/control-plane-evidence-20260731/spike-decision-05.json`，SHA-256 `ed9a005e8e7eca786ee1ae03a2984673bed0ef877361fb471b3d99c46108fe3c`。
- 正式 Phase 1 evidence root：`research/.validation-tmp/control-plane-phase1-20260731-03/`。
- `fault-matrix.json`：固定 seed `20260731`，K1、K2、K3、K8、K9 各 100/100，0 failure；K1-K3 为真实 DBOS SQLite，K8-K9 为 fake-host/filesystem，source digest 起止一致。
- `managed-probe-02.json`：Python 3.13.5/DBOS 2.29.0，重复提交仍为单一 `action_id=workflow_id`、单 workflow row；状态保持 terminal，三件套备份恢复及双库 integrity check 通过。
- `phase-tests-02.json`：58 tests、0 failures；`core-validation.json`：Core `0.8.1-beta.1` package validation passed。
- 最终 decision：`phase1-decision.json`，SHA-256 `4fbb142f5cc7b46b5619f93705dede9642004b4208bcf7cec6d1db313e76af2b`；五个 deterministic checks 均为 true。
- `control-plane-phase1-20260731-01/02/` 及 `-03` 中较早的 `managed-probe.json` 是保留的 blocked/中止尝试，记录 terminal outbox 回退和 verifier 补强过程；不得覆盖或作为最终正向证据。

## 当前阻塞层与下一动作

当前阻塞层：Phase 1 无剩余实现阻塞；Phase 2 尚未建立独立 goal。

下一可自动执行动作：依据 Phase 1 go receipt 建立独立 Phase 2 goal，只实现真实 AppServerAdapter、canonical thread 与 response-gap 调和；不得据此发布或提前进入 Phase 3-5。

## 尚未观察

- 真实 Codex AppServerAdapter、canonical thread response-loss 与三方调和；属于 Phase 2。
- scheduler、cooldown、supervisor、独立 reviewer 和 release aggregate；属于 Phase 3-5。
- 非 Windows 资源验收和默认关闭 `plugin_hooks` 的发布部署策略。
- 本阶段所有 fake host 结果均不证明真实 Codex auto-resume。
