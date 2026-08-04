# DS Lite 控制面 Phase 0/0.5 实施状态

最后更新：2026-07-31

## 当前阶段

Phase 0/0.5：证据解除完成，最新结论为 **go（仅允许建立独立 Phase 1 goal）**；`release_allowed=false`。
## 已观察事实

- 工作树包含既有的大量修改和未跟踪文件；不得 reset、clean、覆盖或删除。
- 实际可执行 `codex --version` 为 `0.128.0`；现有 Core 代码和部分验收工具固定 `0.144.5`。
- 已保存 `0.128.0` 生成 schema，`SHA256SUMS` 摘要为 `9e22b7c4174cdaa87fc3240bce6bfecf8855f263eddfed3e97e49cb165527afb`。
- marketplace 指向 `plugins/deepscientist-lite-core/`；隔离 host 已真实安装 `0.9.0-beta.1`，并在启用隔离 `plugin_hooks` feature 后观察四类 Hook。
- Core Hook 的 stdout 投影包含严格 `hookSpecificOutput`、Stop block 非空 `reason` 与同 turn 单次修复；真实宿主收据已观察 block/allow 序列。
- Stop Hook 不执行持续 controller；旧 `app_server_continuation` 已降级为永不 passed 的 legacy harness，不再发送第二个 `turn/start`。
- DBOS `2.29.0` 已锁定在仓库临时验证目录；controller、domain bridge、K1–K6 harness、SQLite recovery 和资源 receipt 均已存在并复核。
- 现有 acceptance state 和 formal aggregate 均不允许 release；它们是历史状态/receipt，不是本次 Phase 0/0.5 通过证据。

## 保护边界

- 不重跑或覆盖冻结 identity、历史 receipt、研究目录或用户既有改动。
- 不使用 `--last`，不在 resume 不确定时隐式创建 thread/turn。
- 不将 fake/offline 结果写成真实 Codex、Hook 或自动续跑证据。
- 不在本阶段启动 Phase 1-5、push、发布、系统服务安装或凭据操作。

## 下一可自动执行动作

基于 `spike-decision-05.json` 建立独立 Phase 1 goal；不得在本目标内继续 Phase 1–5，也不得据此发布。

## 尚未观察的能力

- 非 Windows 平台的 DBOS 资源数据；现有 WSL 为 Python 3.12.3，但没有 pip/DBOS，本轮未安装。
- Phase 1–5 完整控制器与 release profile；Phase 0.5 的 go 不证明这些能力。
- 无协议专用 developer instructions 时，模型是否能稳定完成同 turn 修复；本轮只验证 Hook 协议链。

## 先前决策：spike-decision-02

当前阶段：Phase 0 与 Phase 0.5 已完成本轮 spike；结论为 **no-go**，`release_allowed=false`。

### 已落地且已复核

- Hook 不再在 `UserPromptSubmit`、`PostToolUse` 或 `Stop` 内执行自治控制器；首次不完整 Stop 仅请求同 turn repair，`stop_hook_active=true` 时交接而不无限 block。
- 遗留 `app_server_continuation` 已降级为 `ds-lite.legacy-stop-first-continuation.v1`，永不产生 passed，也不再发出第二个 `turn/start`。
- 固定 `codex-cli 0.128.0` 生成的 schema，`SHA256SUMS` SHA-256 为 `9e22b7c4174cdaa87fc3240bce6bfecf8855f263eddfed3e97e49cb165527afb`；新 CLI 使用默认 `stdio://`，不接受遗留 `--stdio`。
- 最小 domain bridge 已覆盖 action/outbox/workflow binding/lease fencing，`action_id == workflow_id`；K1-K6 的 fake-host 固定种子 `20260731` 各运行 100 次且全部通过。
- DBOS `2.29.0` 与解析依赖已在仓库临时验证目录实际安装、导入并锁定；控制器目录具备 lock、来源、notice 与 SPDX SBOM。
- Windows 资源数据已写入 `research/artifacts/control-plane-phase0.5-20260731/resource-probe-01.json`。

### 未观察与 no-go 理由

- 所有三次 canonical thread smoke 均在子进程协议开始前关闭，未获得真实 `thread/start/resume/list/read/archive/unarchive` 生命周期或 canonical thread identity；不得把 schema 或手工 initialize 输出写成该能力已通过。
- 当前真实 app-server 明确报告本仓库项目配置/Hook 未被信任；没有真实 `Stop:block -> 同 turn repair -> Stop:allow` receipt。
- DBOS 已安装和导入，但未在真实 durable backend 上观察 workflow recovery；只有 SQLite domain/fake-host spike。
- 仅测得 Windows；其他平台资源结果未观察。

### 证据与完整性

- 正式 decision：`research/artifacts/control-plane-phase0.5-20260731/spike-decision-02.json`。
- `phase-tests-01.json` 因旧 PowerShell 不支持静态 SHA API 而错误写成空 cases；该不可覆盖文件已排除。有效替代是 `phase-tests-02.json`，decision receipt 显式记录其 supersession。

### 下一可自动执行动作

保持 no-go，等待可被信任且可维持双向 stdio 的真实 Codex app-server/Hook 宿主环境；在该前置条件具备后，仅重跑 canonical thread smoke 和 Hook in-turn repair 验收，再重新生成新的 decision receipt。不得以 fake-host 结果解除 release gate。

## 最新决策：spike-decision-05

最新 write-once receipt：`research/.validation-tmp/control-plane-evidence-20260731/spike-decision-05.json`，SHA-256 为 `ed9a005e8e7eca786ee1ae03a2984673bed0ef877361fb471b3d99c46108fe3c`。`spike-decision-03/04.json` 均保留不改写；`-05` 使用最终 fresh 阶段测试和 Core 包验证收据。

### 已实际观察

- `canonical-thread-smoke-13.json` 在 Codex `0.128.0` 生成 schema 下，精确观察 `thread/start/list/read/archive/unarchive/resume`、单一 turn identity 与最终 archive；没有 `--last` 或 resume 后隐式 start。
- `hook-in-turn-repair-smoke-12.json` 在隔离 home、本地 marketplace 与隔离 trust 下，分别记录插件安装前后状态，并真实观察同一 turn 的 `Stop:block -> host same-turn repair -> Stop:allow`；controller `turn/start` 计数为 1，两个 Stop reason 均非空。
- `dbos-sqlite-recovery-05.json` 在 DBOS `2.29.0`/Python `3.13.5`/SQLite 下真实终止起始进程并由新进程恢复同一 `action_id == workflow_id`；workflow 仅一行，旧 fence 被拒绝，新 fence mutation 已持久化。

### 仅 fake/offline 通过

- `fault-harness-02.json` 的 K1–K6 使用固定种子 `20260731`，每个切点 100 次全部通过；它仍是 fake-host 证据，不能冒充真实 Codex fault 证据。
- `phase-tests-05.json` 的 12 个 Phase 0/0.5 模块与 `core-validation-02.json` 通过。

### 资源与剩余边界

- Windows 观测：DBOS 安装净增 `42658638` bytes，导入 RSS `62029824` bytes，CPU `0.421875` 秒，100 actions 控制 SQLite 增长 `40960` bytes。
- WSL 仅确认 Python `3.12.3`，无 pip/DBOS；未安装依赖，因此非 Windows 资源仍是发布前置条件。
- 插件 Hook 在 Codex `0.128.0` 中需要隔离进程显式启用 `plugin_hooks`；默认 feature 状态为 disabled。该事实必须进入 Phase 1 的部署设计。
- 本轮 `spike_decision=go` 只允许创建独立 Phase 1 goal，`release_allowed` 继续为 `false`。
