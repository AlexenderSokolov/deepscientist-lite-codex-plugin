# DeepScientist Lite Codex Plugin

## Phase 5 control-plane status (2026-08-01)

- Phase 5 keeps domain schema v4 and adds observed-runtime selection instead of a fixed historical
  checksum: the chosen Codex binary, generated schema bundle, Python, DBOS, and platform identity
  must match. New stable actions use `run_codex_action_v2`; v1 workflow registrations retain their
  original recovery semantics.
- The current acceptance runtime is Codex stable `0.146.0`, Python `3.13.5`, and DBOS `2.29.0` on
  Windows, with Python `3.12.3` measured on Ubuntu 24.04/WSL. Raw Phase 5 experiments have observed
  Windows/WSL runtime and resources, DBOS 2.28-to-2.29 recovery, user-level supervisor behavior,
  real-host process chaos, loopback disconnects, and synthetic-provider 429/5xx classification.
  These raw receipts are prerequisites, not candidate-bound release evidence.
- Fresh matched-effect pilot `phase5-matched-effect-20260801-15` completed 18 logical calls using
  `gpt-5.6-sol`, with one explicitly authorized retry only after reconciliation proved the failed
  attempt had zero tokens and no workspace effect. A projectless Desktop blind reviewer scored all
  12 aliases once. The deterministic report is `descriptive-improvement-supported`: four expression
  dimensions are favorable against both controls, unsupported completion did not increase, and task
  correctness was not materially worse. Public-response safety scanning found no credential, URL,
  or private absolute-path pattern.
- The final immutable candidate and all 16 current-candidate revalidation receipts are assembled only
  after the full repository regression. Until both the legacy 15-gate aggregate and control-plane
  aggregate pass for that exact digest, the authoritative project state remains
  `release_allowed=false`. Publication, tag, push, and marketplace release remain unexecuted.

## Phase 4 control-plane status (2026-08-01)

- Domain schema v4 makes evidence sets, verifier runs, independent review results, gate decisions,
  release profiles/decisions, private witness indexes, and integrity incidents durable domain truth.
  Worker or model text cannot directly set `passed` or `release_allowed`; only deterministic gate and
  release aggregates may emit those conclusions, and every projected conclusion carries a source.
- Evidence manifests reject path escape, symlinks/reparse points, oversized or unsupported artifacts,
  credential-like fields, environment snapshots, and raw stderr/transcript paths. Raw reviewer output
  stays in the isolated private spool; formal receipts retain only bounded metadata and digests.
- The real reviewer smoke used Codex `0.146.0-alpha.3.1`, schema digest
  `0e79541ba5af824864df3bd14c35ea2678009bce1a6864a3ce6213d9f0228509`, model
  `gpt-5.6-sol`, and explicit `ambient-home`. It observed an independent reviewer thread with
  `sandbox=read-only` and `approvalPolicy=never`, a denied write canary, unchanged artifact bytes,
  and a terminal sidecar without inspecting, copying, displaying, or modifying credentials.
- Four external-process receipt/index crash cuts passed 100/100 fixed-seed trials. Backup v5 restores
  the domain DB, DBOS DB, receipts, protocol journal, supervisor witness, evidence manifest, private
  spool hashes, and release decision into a new directory, failing closed on missing or drifting input.
- Phase 4 passed with write-once receipt
  `research/.validation-tmp/control-plane-phase4-final-20260801-10/phase4-decision.json`
  (SHA-256 `83e32bb80a20989161412fc83ff85736f85ab7b8c50479da046cb7b7dc611f5a`).
  It permits an independent Phase 5 goal only. The real project aggregate remains blocked on Phase 5
  evidence and `release_allowed=false` remains authoritative.

## Phase 3 control-plane status (2026-07-31)

- Domain schema v3 adds DAG scheduling, bounded concurrency, durable cooldown/circuit state,
  gate-local failure isolation, supervisor heartbeat truth, explicit handoff lineage, and TTL-based
  recovery of an expired running claim without changing its action/workflow identity.
- K10 and K11 passed 100/100 fixed-seed external-process trials. A separate supervised probe killed
  one controller generation, recovered the same action with a newer fence, converged two gates, and
  restored the v4 control/DBOS/receipt/journal/supervisor backup into a new directory.
- Phase 3 passed with write-once receipt
  `research/.validation-tmp/control-plane-phase3-final-20260731-03/phase3-decision.json`
  (SHA-256 `6fba9ca1417efa3a36faecf45d852b902ddc8a57481dfacc50be112b143a1341`). Its real
  multi-gate smoke used Codex `0.146.0-alpha.3.1`, schema digest
  `0e79541ba5af824864df3bd14c35ea2678009bce1a6864a3ce6213d9f0228509`, and `gpt-5.6-sol`.
  It proved two independent canonical threads, one intentionally dropped response reconciled after
  controller process changes, two total `turn/start` calls, TTL fence takeover, and one tool side effect.
  The earlier provider timeout was an artifact of a forced isolated `CODEX_HOME`; the accepted real path
  is explicit opt-in `ambient-home`, which neither reads, copies, displays, nor modifies credentials.
  `phase4_goal_allowed=true`; `release_allowed=false` remains authoritative.

## Phase 2 control-plane decision (2026-07-31)

- Domain schema v2 adds fenced canonical thread bindings, durable RPC request states,
  and an append-only protocol journal. `run_codex_action_v1` is new; the Phase 1
  `run_action_v1` contract remains unchanged.
- A loopback, token-authenticated fault broker owns the pinned Codex 0.128.0
  app-server and an fsync/hash-chained wire journal while bounded controller
  workers reconnect. It never falls back to `thread/start` and replays an exact
  logical request instead of dispatching a second `turn/start`.
- The real acceptance observed one app-server and canonical thread across four
  controller PIDs, exactly three logical turns, a dropped real `turn/start`
  response reconciled to the original terminal turn, and a dropped archive
  response reconciled to one archived state. Offline K4-K7/K12 remain separately
  classified fake-host evidence.
- `research/.validation-tmp/control-plane-phase2-continuation-20260731-06/phase2-decision-03.json`
  is the current write-once decision: go, SHA-256
  `9b867e230f4edcafd35750fc0b0fd115da642b8cb86ae649aa83b4e2ed66eb4e`.
  It permits an independent Phase 3 goal only; `release_allowed=false`.

## Cross-system execution rule

Executable wrappers are ASCII-only and pass paths and prompts through argv to
formal Python CLIs. Run `teaching/run_cross_system_validation.ps1` or the Bash
equivalent for encoding, format, shell syntax, and argv checks.

## 研究背景

本仓库实现一个面向教学、快速启动和小型科研项目的轻量 Codex 插件。它抽取 DeepScientist 工作流中可恢复、可审计、可教学的文件协议，不复制 daemon、Web/TUI、connector、MCP 或长期调度平台。

面向维护者的完整设计复盘、证据分层、开发演进与后续路线图见
[`docs/maintainers/development-retrospective-and-roadmap.zh.md`](docs/maintainers/development-retrospective-and-roadmap.zh.md)。该文以 2026-07-31 工作区为观察截点，明确区分已发布/已验收事实、当前工作区实现与待验证设想。

根目录 `PROJECT.md` 是本仓库的长期项目记忆；`plugins/deepscientist-lite/assets/templates/PROJECT.md` 是插件为用户项目生成的合同模板，两者职责不同。

## 当前扩展边界（2026-07-27）

- Web 包的 OpenCLI 集成仅是 capability-discovered 的 `opencli-cli` challenger；只接受 manifest 中 `access=read`、`strategy=PUBLIC`、`browser=false` 的适配器。Chrome Bridge、daemon、profile、登录态、Cookie、表单和上传不属于 DS Lite Web v1。
- `tools/validation/acquire_pinned_codex.py` 在隔离 `TEMP_ROOT` 获取并校验 Codex 0.144.5；通过 npm integrity 和冻结二进制 SHA 后，才可用于真实 Hook/provider/Desktop 验收。
- 真实验收 receipt 必须按 source、offline、cli、provider、hook、delegation、matched_effect、formal_cache、fresh_desktop、openscience、docs 独立记录；任何宿主门不能由离线或相邻后端证据推断。
- 控制面 Phase 0/0.5 固定 Codex CLI/app-server `0.128.0` 生成 schema 与 DBOS `2.29.0`。最新 `spike-decision-05.json` 为 go，但仅允许建立独立 Phase 1 goal；`release_allowed=false`，非 Windows 资源仍未观察。
- 控制面 Phase 1 采用双 SQLite 边界：`.ds-lite/control.sqlite3` 由 DS Lite migration 管理领域真值，`.ds-lite/runtime.sqlite3` 由 DBOS `2.29.0` 管理 durable workflow；两库不伪装原子事务，通过稳定 `action_id=workflow_id`、transactional outbox、reconcile-before-dispatch 和 fencing 恢复。`phase1-decision.json` 已基于 K1-K3/K8/K9 各 100 次、managed duplicate submission、三件套备份恢复、58 tests 与 Core validation 给出 go；它只允许独立 Phase 2 goal，`release_allowed=false`。

## 基本假设

- 文件化项目合同、artifact 和显式状态图足以支持短周期科研工作的跨会话恢复。
- 状态内核应保持 Python 3.10+ 标准库实现，避免增加教学部署成本。
- Graph JSON 是机器权威状态，`RESEARCH_MAP.md` 是可重建的人类投影。
- 失败实验、旧路线和公开决策理由应保留，但不得记录隐藏思维链。

## 分析目标

- 可靠维护 intake、scout、idea、experiment、review、analysis/write 与单轮 iterate 的最小科研闭环。
- 将 AIResearch 暴露出的失败模式固化为协议规则：artifact 不是进度，ready 不是完成，idea 不是实验，metric 方向错误是协议失败，没有可见闭环就没有智能体体验。
- 防止并发覆盖、非原子写入、路径泄露和证据关系污染推进路线。
- 保持 Windows 与 Unix-like 环境中的命令、中文和空格路径可用。
- 为教学 Beta 提供可重复验证、证据审查、迁移和发布流程。
- 用领域中立 Factor Card 比较科研 idea 的新颖性、可行性、证据、成本、风险与任务对齐，同时抑制单一分数和自动真值错觉。
- 用显式批准、互斥路径所有权和独立 result ref 管理一次最多三个任务的有界协作，同时保持父 worker 的唯一整合责任。
- 用四案例、三 arm 的 matched pilot 比较工程连续性、反例保留、多 seed 解释和创新评价；准备态、真实执行态与发布证据必须分开。
- 用统一入口、单轮 reflective iteration、派生假设池、轻量 Hook helper 和 start/progress/end 协议改善长任务中的可见性、责任归属与失败恢复。

## 工作流程

1. 历史单体候选曾通过九个 `ds-lite-*` skills 加十七个 `nature-*` skills 提供 26 个入口；当前 marketplace 已拆分为 Core 9、Academic 17，以及四个各 1 入口的领域包。`$ds-lite` 对已批准的多 gate 项目启动前台控制器，连续推进所有独立 ready gate；只有用户明确要求单步、只规划或无副作用时才路由到一个动作 skill。
2. 先写 artifact、memory 或可复现 `run_*.sh`，再调用状态 CLI。
3. Graph 写操作在锁内检查 revision、校验语义并原子替换。
4. 实验先生成 contract/Evidence Pack，再由独立 review 流程决定是否进入 analysis/write。
5. 每个有界任务由 `research/work-unit.json` 的 `ds-lite.work-unit.v1` 描述；claim-bearing evidence 只由 profile typed validator 升级，review 同时写 Markdown 和 `ds-lite.review-result.v1` sidecar。
6. idea 比较可写 `ds-lite.factor-card.v1` sidecar；六个分项独立保存证据与不确定性，no weighted total，且卡片只作为 decision artifact。
7. 可独立拆分的工作使用 `ds-lite.delegation.v1`：先验证计划并等待明确批准，再由最多三个子任务按互斥路径回传，父 worker 核验并整合；不可拆分工作保持单 worker。
8. `$ds-lite-iterate` 在动作前登记 `ds-lite.iteration.v1` running receipt，执行一个动作后验证、反思、汇报并进入终态；该最小接口不是 exactly-once transaction。
9. 每次 graph 提交后重建 `RESEARCH_MAP.md`；`mission` / `render-status` 把 `latest_iteration` 与派生 `hypothesis_pool` 投影到 `STATUS.md`。
10. 使用统一验证脚本执行单元测试、仓库 smoke 和语法检查。
11. 用户文档按“README 快速上手—用户指南理解机制—实现文档维护细节”分层；教学课程用标准库 runner 准备确定性现场。

## 代码结构

- `plugins/deepscientist-lite/`：可安装插件、技能、模板、协议和状态脚本。
- `plugins/deepscientist-lite/scripts/ds_lite_iteration.py`：最小 reflective iteration 的 init/finalize/verify helper。
- `plugins/deepscientist-lite/hooks/` 与 `scripts/ds_lite_hook.py`：可选轻量 Hook 配置和脱敏 helper。`Hook fresh-host` 证据必须按固定 Codex 版本、隔离身份和真实事件 receipt 独立判定，不能由源码或 fake host 推断。
- `tests/`：Graph v2、CLI、迁移、并发和路径回归测试。
- `tools/validation/`：仓库级验证器与 shell/PowerShell 入口。
- `docs/`：设计、迁移、已知问题和发布维护资料。
- `teaching/`：不进入运行时包的课程与演示材料。
- `teaching/lab_runner.py`：跨平台课程准备器；七个协议 lab 支持 student/reference，matched pilot 只生成隔离 student workspaces 与独立教师材料，不预写模型结果。
- `teaching/pilot_runtime.py`：授权后的 matched pilot 冻结、双 home 隔离、preflight/单次 canary、18 次串行执行、脱敏 receipt 和 fail-closed resume。
- `teaching/pilot_score.py`：只读公开产物的自动评分与 incomplete/待盲评报告；不读取完整会话或隐藏推理。
- `teaching/app_server_transport.py`、`canonical_thread_smoke.py` 与 `hook_in_turn_repair_smoke.py`：0.128.0 schema 驱动的双向 stdio、canonical lifecycle 和真实同 turn Hook 验收；禁止 `--last` 与失败后隐式 start。
- `plugins/deepscientist-lite-core/controller/`：版本化 domain schema、lease/fencing、transactional outbox、DBOS workflow bridge、write-once receipt、managed CLI、备份恢复、K1-K12 fault harness，以及 Phase 2 的 schema-bound Codex adapter 与可重连 fault broker、Phase 3 的 DAG/failure policy/cooldown/supervisor。broker 仅是协议故障验收和前台 controller transport，不是后台 supervisor。

## 运行流程

- Unix-like：`bash tools/validation/run_validate.sh`
- PowerShell：`powershell -ExecutionPolicy Bypass -File tools/validation/run_validate.ps1`
- 单元测试：`tests/run_tests.ps1` 或 `tests/run_tests.sh`；两者都通过
  `tests/run_unittest.py` 统一安装项目盘临时目录策略。
- 仓库 smoke：`python tools/validation/validate_repo.py`
- 教学课程：`python teaching/lab_runner.py --lab quickstart --mode student --output <path>`
- 行动与反思：`python teaching/lab_runner.py --lab action-reflection --mode student --output <path>`
- 对照 pilot：`python teaching/lab_runner.py --lab matched-pilot --mode student --output <path>`
- 真实 pilot：`powershell -File teaching/run_pilot.ps1 -Action prepare|install|preflight|canary|run|resume|score`，或 `bash teaching/run_pilot.sh <action>`；关键路径、pilot ID、授权引用和 CLI 必须显式提供。`install` 只建立隔离 skill home，不是 cache 安装；失败/超时/ambiguous 不能用 resume 重试。
- 控制面 Phase 0.5 复验：显式设置 `CODEX_BIN`、`SOURCE_CODEX_HOME`、`DBOS_DEPENDENCY_ROOT`、`EVIDENCE_ROOT` 与 provider 环境后运行 `bash run_control_plane_phase05.sh`；`EVIDENCE_ROOT` 必须是全新目录，脚本不安装依赖、不覆盖 receipt。
- 控制面 Phase 1 复验：显式设置 `PYTHON_BIN`（固定 Python 3.13.5）、`DBOS_DEPENDENCY_ROOT`（DBOS 2.29.0）和全新 `EVIDENCE_ROOT` 后运行 `bash run_control_plane_phase1.sh`；Windows 使用 `run_control_plane_phase1.ps1`。入口依次运行 fault matrix、managed/backup probe、阶段测试、Core validation 和 write-once decision，不接真实 Codex。
- 控制面 Phase 2 continuation 复验：显式提供固定 Python 3.13.5、DBOS 2.29.0、Codex 0.128.0 binary 和全新 evidence root，运行 `run_control_plane_phase2_continuation.ps1`；Bash 使用同名 `.sh`。入口运行 fake fault matrix、Phase 0/0.5 contracts、Phase 1/2 tests、真实 response-drop/controller restart、broker-aware backup、doctor、Core 和 write-once decision。
- 控制面 Phase 3 复验：显式提供固定 Python 3.13.5、DBOS 2.29.0、Codex 0.128.0 binary 和全新仓库内 evidence root，运行 `run_control_plane_phase3.ps1`；Bash 使用同名 `.sh`。入口即使遇到单个真实宿主失败也会继续 fault matrix、supervised backup、资源、阶段测试和 Core，最终只由 write-once decision assembler 判定 go/no-go。

### 2026-07-24 wire/CLI fresh gate

Fresh `communication-beta2-20260724-wire-01` passed the pinned 0.144.5
Responses wire gate with one authenticated request, terminal output, nonzero
usage, and no retry. Fresh `communication-beta2-20260724-gated-cli-02` then
passed the formal one-shot CLI canary with 26 skills, terminal completion,
final feedback, 16 tool events, nonzero usage, and an unchanged workspace.
The first Hook host attempt was blocked before process start by the provider
trust policy because workspace context would be sent to an untrusted external
destination. Hook, Desktop, delegation, matched effect, formal cache, and
release remain unverified; do not retry until the destination is explicitly
trusted.

## 验收标准

### 交接与 CLI 边界

- `teaching/handoff_protocol.py` implements `ds-lite.handoff.v1`: long-context and child-task handoffs carry only redacted facts, hypotheses, authorization, non-secret configuration, relative evidence refs, failure layer, unverified items, and one next action. The digest must match before a receiver may act.
- `teaching/cli_compatibility.py` implements `ds-lite.cli-compatibility.v1`: PowerShell, cmd, Git Bash, WSL/Linux Bash, and external hosts are separate surfaces; quoting, encoding, PATH, WSL translation, `.cmd` child processes, and pipe closure are classified without retaining raw commands or output.
- `teaching/fresh_host_probe.py` performs exactly one fresh CLI process probe, records a terminal redacted receipt even for zero events or timeout, and refuses retry or overwrite.
- `communication-beta2-20260720-host-02` used this probe once: process and pipes terminalized, zero JSONL events, failure class `unknown`, and no retry. This is a frozen process-boundary observation, not Hook or Desktop host evidence.
- `communication-beta2-20260720-host-03` ran only model-free `--version`, `features list`, and `plugin list --json` checks. All three started and exited with closed pipes; no external model request was made. This proves CLI-start only, not plugin loading, Hook, Desktop, delegation, matched effect, or release.
- `communication-beta2-20260720-host-04` repeated the same model-free checks with pinned Codex `0.144.5` and SHA-256 `EFDB3540EF74B9909408C8D38DA79483454797B36F471E3E004FC2BF2B70E22A`. All checks passed with closed pipes and no model request. This upgrades only the pinned CLI-start evidence; Hook loading, Desktop, delegation, matched effect, formal cache, and release remain unverified.
- `communication-beta2-20260720-host-05` installed the candidate through a fresh isolated marketplace and observed nine skills plus `hooks/hooks.json`. A single pinned CLI task exited with code 2 before producing any Hook event receipt; raw output was discarded and the identity is frozen. This does not distinguish the CLI failure message and does not prove Hook loading.
- `communication-beta2-20260720-host-06` repeated the installation with the CLI wrapper corrected for `0.144.5` and observed one real `UserPromptSubmit` Hook receipt. The task then timed out before PreToolUse, PostToolUse, or Stop; raw output was discarded and the identity is frozen. This is partial loader evidence, not complete Hook acceptance.
- `communication-beta2-20260720-host-07` used a corrected root-level TOML composition and passed pinned model-free CLI checks with the installed candidate. A real provider task was not started because the execution policy rejected sending workspace context to the configured external provider; this is an authorization boundary, not a product pass/fail.
- Fresh offline protocol acceptance `offline-acceptance-20260722-host-boundary` passed fake transport, fake Hook, delegation, and matched-preparation gates. It explicitly keeps real provider, real Hook loading, child dispatch, effect measurement, and release gates locked.
- `teaching/run_trusted_hook_host.ps1` and `.sh` are the controlled continuation surface for a tenant-trusted execution environment. They require the pinned Codex SHA, fresh host paths, and write only redacted Hook event summaries; they do not bypass provider trust policy.
- `teaching/run_trusted_hook_host_local.ps1` is the user-facing one-shot launcher: it discovers/validates pinned CLI, prepares fresh marketplace/cache and root-level route TOML, then delegates to the redacted Hook runner. Existing output roots are refused.
- Selective Superpowers adaptation is process-only: skill applicability, short plan, TDD, bounded action, verification, and explicit handoff. It does not add daemon, queue, MCP, hidden state, or automatic retry.

- Graph v2 写入具备跨平台锁、revision 检查和原子替换。
- 节点更新时间在宿主 wall clock 短暂回退时不早于已有 `created_at/updated_at`，Graph 时间不变量继续严格生效。
- v1 可读且可迁移，原 graph 备份永久保留；外部绝对路径不会被静默写入 v2。
- progression trace 不遍历 `supports`、`blocks` 或 `rollback`。
- 九个技能的结构和元数据可验证；涉及 graph 的技能只通过 CLI 修改 graph 并处理 revision 冲突，`ds-lite-iterate` 一次只推进一轮并停在 checkpoint。
- Evidence Pack 不保存凭据或本机绝对根目录，项目内证据可通过 SHA-256 复核。
- 新的 experiment→analysis 路线经过 review；旧 Graph v2 仍可读并仅产生兼容警告。
- 新项目无 claim requirement 时为 `planning`；普通 artifact/log/path 不升级证据。只有 profile typed validator 通过才能到 `has-evidence`，只有匹配的 typed review result 才能到 `reviewed`。
- Factor Card 正例、缺字段、错误 enum、路径逃逸、敏感字段、ID/因子冲突和 `extensions` forward compatibility 均有测试；卡片不能升级 evidence strength。
- Delegation 正例、缺字段、错误 enum、路径逃逸、敏感字段、ID 冲突、路径重叠、批准门、terminal result ref 和 `extensions` forward compatibility 均有测试；真实子智能体行为仍需单独授权验收。
- Windows PowerShell、Git Bash、WSL DrvFS、WSL ext4，以及远程 Windows/Ubuntu CI 均通过统一验证入口。
- manifest、技能、模板、文档和发布版本保持一致。
- `ds-lite.iteration.v1` 覆盖终态、action/reflection/user report、revision、路径、敏感字段、ID 冲突、未知字段和 `extensions`；Mission Board 的 `latest_iteration` 与 `hypothesis_pool` 可从公开 sidecar 重建，未测量假设保持 `untested`。
- Hook helper 覆盖非工作区放行、脱敏状态附着、Graph 直改/危险命令/tmux 扩容阻断、合法 CLI 放行和 Stop 单次续跑；Codex `0.128.0` 隔离 fresh host 的插件 Hook 加载与同 turn repair 已有独立 receipt。
- Codex `0.128.0` 的真实隔离验收已观察四类插件 Hook 加载，以及同一 turn 的 `Stop:block -> repair -> Stop:allow`；该门使用协议专用 developer instructions，只证明 Hook 同 turn 控制链，不证明通用自治修复质量或 release readiness。
- 七类协议教学实验可在 student/reference 模式运行；matched pilot 可确定性准备 4 案例 x 3 arm，三 arm 输入摘要一致、结果保持 pending，且公开文档不把 Graph 说成推理链快照，不把 Evidence Pack 完整性说成科学真实性。
- `ds-lite.matched-pilot-execution.v1` 覆盖正例、缺字段、错误 enum、路径逃逸、敏感/隐藏推理字段、ID 冲突、未知字段与 `extensions`；fake Codex 证明原始 JSONL、reasoning 和 stderr secret 不落入 receipt。

- 2026-07-23 真实 wire 诊断使用三个全新身份且每个身份只发起一次 provider 请求：`loop-wire-02` 的 baseline 为 HTTP 400/4xx，`loop-wire-03` 仅增加 Codex Responses Lite header 后仍为 HTTP 400/4xx，`loop-wire-04` 在保留 header 的同时将 input 改为 Codex `message[]` 后变为 HTTP 502/5xx。三次均连接建立、响应头收到、terminal=false、usage=0、自动重试=false，均冻结为 `protocol`；没有创建 CLI canary 或任何后续真实宿主门。静态核对 `rust-v0.144.5` 源码确认 `use_responses_lite=true` 时 header、数组 input、`store=false`（非 Azure）和附加请求字段的差异；这解释了形状变化，但尚未证明 provider wire compatibility。
- 本轮新增 `wire_probe` 的固定 rejection projection（auth/model/parameter/input-shape/path/protocol/unknown）、显式 header/input 变体和离线 `codex-lite-minimal` request profile；不保存原始 response、message、URL、prompt 或认证值。后续加入 Loop offline orchestrator 后，完整 unittest 实际运行 `289/289` 通过；profile 尚未连接真实 provider，真实 release、Hook、Desktop、delegation、matched effect、formal cache 仍保持 `not-verified`。

## 设计决策

- 当前发布线：`0.4.0-beta.2`，Graph schema 继续为 `ds-lite.graph.v2`，Evidence schema 为 `ds-lite.evidence.v1`；Mission Board 是派生投影，不是新 schema。
- P0 引入独立 `ds-lite.work-unit.v1` 和 `ds-lite.review-result.v1` sidecar，不改变 Graph v2 或 Evidence Pack v1。`verdict` 表示 review gate，`claim_assessment` 表示 claim readiness；未知 schema 字段只允许放在 `extensions`。
- 通用 core 只面向科研与工程任务。`literature-evidence`、`mathematical-exploration`、`software-evaluation`、`numerical-simulation` 仅保留为 `reserved / not-validated`，不得据此宣称领域支持。
- `ds-lite.factor-card.v1` 固定六个科研/工程通用分项，不计算总分或自动赢家。Finance Factor 只保留为方法来源与 pressure-case fixture；WQ、Qlib、股票池和金融指标不进入 core、模板或默认 skill。
- `ds-lite.delegation.v1` 只描述一次有界协作：最多三个任务、`parallel|sequential`、明确用户/OpenScience 批准、互斥路径所有权、`nested_delegation=false`、独立 result ref 和唯一父级 integration owner。它不提供 daemon、队列、scheduler、后台 worker 所有权或自动重试。
- 项目外资源使用 `external://alias/path`，绝对根目录由 `DS_LITE_EXTERNAL_<ALIAS>` 提供。
- 保留 `DeepScientist Lite` 名称，但明确声明为独立、非官方第三方插件。
- v0.2 不引入 MCP、daemon、Web/TUI、模型路由或长期 automation。
- `run_validate.sh` 必须兼容只有 `python3` 的 Unix/WSL 环境；运行时脚本保持 LF。
- CLI 文件内容固定使用 UTF-8；验证入口启用 Python UTF-8 模式，CLI 输出在旧 Windows 代码页下必须可安全转义，不能依赖宿主区域设置。
- 节点 mutation 使用已有节点时间作为下界；WSL/虚拟化时钟校正不能把 `updated_at` 写到 `created_at` 之前，也不通过放宽 schema 校验掩盖异常。
- 状态内核模块化属于 v0.2 之后的内部重构，必须保持 Graph v2 与 CLI 兼容。
- Review 是独立流程和 artifact，不宣称独立模型或物理隔离。
- v0.3 不加入 MCP、subagents、HPC/云调度或完整树搜索；评分循环只作为 Graph 分支教学。
- 已发布 v0.4 不加入 daemon、MCP、Web/TUI、hooks 或长期后台调度；当前 `0.8.1-beta.1` Core 增加插件局部、无状态的 Hook helper。Codex stable `0.146.0` 已实际从 `hooks/hooks.json` 自动发现 Hook；源码保留明确指针，确定性发布包投影会移除官方 validator 尚不接受的冗余 `hooks` manifest 字段并保留 Hook 配置。真实同 turn Stop 修复仍必须由独立 receipt 证明。OpenScience 可作为上层主管调用 DS Lite worker，但 DS Lite 只提供文件化任务板、证据门和单轮迭代协议。
- 外部长任务管护采用“稳定外部 owner 管进程，DS Lite 管文件化交接和证据”的责任模型。进程丢失的根因应先按生命周期归属错误排查；对话、Codex worker、tmux、实验进程和工件是五种独立状态。Lite 不拥有进程生命周期，只要求 Codex 登记、检查、备份、修复和恢复 `external-task-*` 记录，不能把临时 shell 内创建的 tmux 当作持久执行证明。
- tmux 容量申请必须先由 Codex 写成 `external-tmux-plan-*`，再由用户从独立稳定 shell 手动创建固定 socket、顶层 session 和计划内 pane；Codex 只验证、连接和使用已授权槽位。“子会话”不是 tmux 协议对象，用户这样表述时只解释为 pane-scoped Codex CLI child worker，其进程存活与 provider 对话可恢复性必须分别验证。
- 教学 runner 只负责确定性准备和协议故障，不冒充 Codex skill 或领域审查；课程默认保留所有输出，不覆盖已有目录。
- Matched pilot 的 plain、scratchpad、DS Lite 三 arm 只改变连续性机制；任务、材料与分轮提示进入同一 SHA-256 输入摘要。真实 12-arm Codex 调用、成本记录和子智能体 forward test 仍需单独授权，静态生成不能写成效果证据。
- 首个已授权真实 pilot `matched-pilot-20260717-01` 冻结为 CLI `0.144.5`、`gpt-5.6-sol/low`、18 次串行计划；第一个 plain 工程调用在 767 秒后 `process-failed`，0 token、无最终消息、0/18 completed。该 pilot 永久保持 blocked，禁止 resume/自动重试，只作为 fail-closed 教学案例；它不满足 `0.5.0-beta.1` 候选门。
- 真实失败暴露的可诊断性缺口已在冻结后修复：未来 failure receipt 只保存 stderr 固定类别、行数和 SHA-256，不保存 stderr 原文。该改动不追溯修改既有 pilot，也不解释其外部根因。
- 第二次 E1 验收 `matched-pilot-20260718-01` 的 preflight 证明固定 CLI、环境认证类别、零/九技能 prompt surface、features、WSL 和源码摘要成立；唯一一次隐式 canary 建立 thread 后以 `rate-limit` 类别、0 token、0 tool、无 turn terminal event/反馈和 `timeout` 结束，工作区未修改，因此本轮冻结且不进入 E2。该现场另行确认并修复了 Windows `.cmd` 超时只杀包装进程、延迟 terminal finalize 的问题；没有重试或手工改写 receipt。
- 教学 runner 完成场景准备后必须从最终 Graph 同步 `STATUS.md` 的 active node 与 revision，不能把初始化状态留给学生当作“故障”。
- 生成的 `run_*.sh` 不保存项目绝对根目录或 Codex cache 路径；本机运行时通过 `PYTHON_BIN`、`DS_LITE_EVIDENCE_CLI`、`DS_LITE_PLUGIN_ROOT` 等环境变量解析。
- 本地 marketplace 写入配置只代表来源已注册；安装须在 `/plugins` 等宿主提供的插件浏览界面中明确完成。缓存验收以新线程实际报告的版本、来源、UI 文案和对应版本技能数量为准：已发布 `0.4.0-beta.2` 为七技能，当前未发布 v0.5 源码为九技能。
- Codex 验收工具只能创建新隔离目录并做只读宿主探测；`package_valid`、`host_supported`、`installation_verified` 和技能发现必须分别记录。
- 真实模型验收按 `prepare → isolated-skill-home install → preflight → one-shot canary` 分级推进。preflight 只检查固定 CLI、认证类别、feature 枚举、control 零技能、DS Lite 九技能 prompt 注入、WSL 与源码摘要；canary 必须是隐式、只读、ephemeral 且只运行一次。trigger、18-call pilot、委派、cache 与发布继续是后续独立授权门。
- 2026-07-20 最小隔离 home 验收 `communication-beta2-20260720-slim-plugin-effect-03` 使用同一认证与模型建立 `control-slim` 与 `ds-lite-slim`；preflight 证明 control 为零技能、DS Lite 为当前源码九技能，三次只读 ephemeral canary 均有 thread/turn/final/usage 且无文件写入。结论只能写为 `slim isolated plugin effect partially verified`：DS Lite 明显增强介入原因、状态检查、blocked fail-closed 与边界说明，但正式 cache、fresh host、Hook loading、完整 campaign、matched A/B 和发布 readiness 仍未验证。详见 `docs/maintainers/slim-plugin-effect-20260720.zh.md`。
- 可解释性验收新增教学层 `teaching/explainability_score.py`：分别记录适用性准确率、误触发/漏触发、理由证据覆盖、验证可追溯、用户决定清晰度、无证据完成和 artifact 可恢复性，不合并成单一智能分数。当前确定性测试已覆盖适用/不适用、状态投影、artifact 非进度、delegation 审批/路径/result ref；真实 12-case matched comparison 和真实宿主子任务仍未验证。
- 2026-07-20 新 pilot `cross-task-explainability-20260720-02` 的隔离 preflight 通过固定 CLI `0.144.5`、provider/auth、hooks/multi-agent/plugins、WSL、control 零技能与 DS Lite 九技能发现；唯一隐式 canary 建立 thread 后在 180 秒以脱敏 `rate-limit` 冻结，0 usage、0 tool、无 terminal/final feedback、workspace unchanged。按 fail-closed 规则未启动 12-case campaign 或真实 delegation，receipt 不重试、不改写。
- 统一验收审计门位于 `teaching/acceptance_gate.py`，通过 `extensions.acceptance_gate` 附着到 pilot receipt；只有完整观察、非零 usage、artifact/state 交叉核验和明确用户报告才可进入下一门。`communication-beta2-20260720-gated-01` 的 canary 因 `rate-limit` blocked；后续 `communication-beta2-20260720-gated-02` 在 route/catalog 已复制且 preflight 通过后，以 `transport` blocked。正式 cache、Hook host、matched comparison 和真实 delegation 仍未验证。
- 隔离 pilot 的 `install_homes` 只复制正式 home 的非敏感 provider 路由和相对 model catalog，并强制 pilot 使用 `gpt-5.6-sol/low` 和 `request_max_retries=0`；认证、token、header 和全局配置不复制。此前 provider 路由缺失导致“模型可解析、真实请求不可用”的设置缺口已由 pilot-runtime 回归测试锁定并修复。旧 canary 仍不可重放，新的真实请求必须使用新 pilot 身份并重新通过 preflight。
- 新 pilot `communication-beta2-20260720-gated-02` 证明 route/catalog 配置复制和 preflight 均成立，但唯一 canary 在建立 thread 后以 `transport` 失败，0 usage、0 tool、无 terminal/final feedback；该结果冻结为 provider 运行时可用性未验证，不得解释为插件表达测试结果。
- `ds-lite.transport-diagnostic.v1` 只保存 allow-listed provider code、HTTP 状态类别、连接/响应头观察、子进程/管道终态、stderr 行数与 SHA-256，不保存 stderr 原文。`ds-lite.offline-protocol-acceptance.v1` 用本地 fake provider + fake Codex 验证七类 transport、零自动重试、Hook fake host、delegation 协议和 matched prepare/freeze；该报告固定 `real_gates_unlocked=false`，不能替代真实 provider、宿主或表达效果验收。
- 2026-07-21 新增真实 wire 诊断身份 `communication-beta2-20260720-wire-diagnostic-01/02`。两次均不读取或改写旧 gated-02；`prepare`、`preflight`、DNS/TCP/TLS 网络层通过，`requires_openai_auth` 和零重试配置被保留。最小 authenticated Responses SSE 请求收到 provider 侧 `4xx` 响应头、无 terminal event、usage=0、单次请求且无自动重试；修正后的诊断将该层归为 `protocol`，而非网络或子进程问题。该真实门冻结，未创建 gated-03，也未验证 Codex CLI wire、Hook host、真实 delegation、matched effect、formal cache 或真实 Agent 表达。
- 2026-07-21 后续真实证据：`wire-diagnostic-03` 的最小 Responses SSE 通过（HTTP 200、terminal event、非零 usage、单请求）；`gated-03` 仍因隔离 route 缺少 `env_key` 而以认证 4xx 冻结；加入非敏感 `env_key=OPENAI_API_KEY` 后，新的 `gated-04` CLI canary 通过（`turn.completed`、最终反馈、14 个工具事件、非零 usage）。`host-01` 通过隔离 CODEX_HOME 的真实 marketplace/add 安装候选版本和 Hook manifest，但 fresh CLI 任务无 JSONL 事件并冻结，因此 Hook host、Desktop fresh task、真实 delegation、matched effect 和 formal cache 仍未验证。
- 默认 `validate --strict` 继续审计全图；当前路线交接可使用 `--scope active-route`，但结构与路径完整性错误始终全局生效，非当前路线警告必须保留在输出中。
- 教学产物使用 `ds-lite.teaching-handoff.v1` 核对 Graph、STATUS、active route 与 revision；该投影不改变 Graph 作为机器权威来源的地位。
- `0.4.0-beta.2` 只发布已验证的 P0 work unit、typed evidence/review 和 worker handoff。未发布 v0.5 已有最小 `ds-lite.iteration.v1`，但 P1 action envelope、canonical idempotency、exactly-once/partial-write transaction、P2 typed external-long profile 与 P3 cache/new-thread/tmux 完整验收继续延期，详见 `docs/maintainers/roadmap.zh.md`；延期项不得被文档或示例描述为已实现。

## 已废弃方案

- Graph v1 的直接覆盖写入与无 revision 并发模型。
- 在 Python 中硬编码初始化文件，与 `assets/templates/` 形成双重来源。
- 使用所有边计算 Active Route。
- 在 graph 中保存项目外绝对路径。
# Cross-system reliability rule

## Real Hook host status (2026-07-23)

Fresh pinned Codex 0.144.5 runs `trusted-hook-02` and `trusted-hook-03` observed Hook event types but only `allow` decisions. `trusted-hook-04` froze during fixture preparation because its first action kind was not registered. `trusted-hook-05` used a valid DS Lite running-iteration fixture and observed real UserPromptSubmit, PreToolUse, and PostToolUse events, but the CLI task ended at `turn.failed` before a blocking PreToolUse or Stop continuation. This is partial Hook loader evidence, not complete Hook acceptance. Real delegation, matched effect, formal cache, fresh Desktop, and release remain not verified. Evidence: `docs/maintainers/real-hook-acceptance-20260723.zh.md`.

## Real Hook event gate (2026-07-27)

- Fresh trusted Host A `trusted-hook-20260727-04` observed real `UserPromptSubmit allow`, dangerous `PreToolUse block`, legal `PostToolUse allow`, and first `Stop block` without the direct Graph edit taking effect.
- Fresh trusted Host B `trusted-hook-20260727-06` used the pinned Codex `0.144.5` SHA identity and a short legal provider turn to observe `UserPromptSubmit allow`, `PreToolUse allow`, `PostToolUse allow`, and closed `Stop allow`; no automatic retry was observed.
- `G:\DS-Lite-validation\trusted-hook-20260727-06\trusted-hook-acceptance.json` aggregates the two frozen pilots without rewriting them. Host B's iteration was intentionally fixture-prepared before the real turn, so `agent_initiated_terminal_closure` remains `not-observed`. This passes the four-event Hook gate only; it does not unlock delegation, matched effect, formal cache, fresh Desktop, or release by adjacent inference.

## Real delegation canary (2026-07-27)

- The fresh, fixed-Codex `real-delegation-20260727-01` provider turn completed with no automatic retry, but the redacted collaboration summary observed two `wait` calls and zero `spawn_agent` calls or child receivers. `multi_agent=stable` in the CLI feature list therefore does not prove that child dispatch is exposed to `codex exec` tasks.
- `G:\DS-Lite-validation\real-delegation-20260727-01\delegation-canary.json` is frozen as `blocked`. A future real delegation attempt needs a distinct fresh Desktop or trusted execution surface that actually exposes `spawn_agent`; it must then separately prove two mutually exclusive children, result references, parent-only integration, and a preserved partial child.

## Real Desktop delegation acceptance (2026-07-27)

- The authorized Codex Desktop execution surface completed `research/desktop-delegation-20260727-02/`. The parent dispatched exactly two child tasks with mutually exclusive output paths, received independent result artifacts, and was the sole integration owner.
- `host_acceptance.audit_delegation` verified two `spawn_agent` calls, two distinct receiver hashes, two independent result references, `nested_delegation=false`, and one parent integration. A separate child was intentionally blocked by a missing formal-cache receipt input; its blocked receipt was preserved without replacement or retry.
- `research/desktop-delegation-20260727-02/delegation-acceptance.json` is the independent passed delegation receipt. The earlier CLI canary remains frozen as a different execution-surface limitation; neither outcome implies matched effect, formal cache, fresh Desktop discovery, or release readiness.

The fresh Loop acceptance receipt `.validation-tmp/offline-loop-acceptance-20260723-final/offline-loop-acceptance.json` records fake `partial -> completed` continuation as passed and `codex-autoresearch` as `blocked-not-verified` with zero external process spawn. It is offline protocol evidence only and does not unlock any real host or release gate.

## Current upstream integration status (2026-07-24)

- The frozen historical candidate is `0.6.0-beta.1`. The active marketplace candidate is split into six packages; the frozen directory is retained only for compatibility evidence.
- Nature integrations are opt-in. `ds_lite_nature_setup.py inventory|doctor|onboarding|apply|verify` checks local tools and environment-key presence, writes only workspace-local `.ds-lite/nature/` files, and never changes global Codex, credential, marketplace, or MCP configuration.
- `codex-autoresearch` is an authorized fixed snapshot at commit `f2389bffbb4cd7789deb6796bc4ba35bf31f2a90` / npm `0.1.5-beta.0`. The adapter preserves bounded goals, completion evidence, zero retry, and fail-closed stopping, but does not execute the upstream CLI until a redacted child-output contract is supplied.
- `tools/validation/upstream_manager.py` inventories every registered upstream, verifies local provenance, and produces read-only update plans. It never overwrites vendor sources or auto-publishes changes.
- Nature skill `source_skill_sha256` values hash UTF-8 text after normalizing line endings to LF. Other vendored files retain byte-for-byte hashes, so provenance remains stable across Windows and Unix checkouts without weakening snapshot validation.
- Offline integration, onboarding, adapter, loop, text-compatibility, cross-system, and repository validation are source-level evidence only. Real provider, Hook host, Desktop, child delegation, matched effect, formal cache, and release gates remain locked.
- Unified validation tests must use explicit provider fixtures rather than inheriting the developer's `CODEX_HOME`; Python 3.10 structured-text validation uses the CI-installed `tomli` compatibility parser when stdlib `tomllib` is unavailable. Ignore rules apply only below the requested scan root, so a clean checkout may itself live under `.validation-tmp` without disappearing from validation. Shell templates under `assets/templates` keep byte and line-ending checks, while Bash syntax is checked only after rendering because the source form intentionally contains template escaping.
- On 2026-07-24 the unified Windows validation entry completed `306/306` unittest cases, repository validation, PowerShell syntax checks, `py_compile`, and `git diff --check`. The fresh cross-system receipt observed 827 files with zero failures; Bash, PowerShell 7, and shellcheck were `not-observed` on this host.

Executable entrypoints (`.ps1`, `.sh`, `.cmd`) are ASCII and only orchestrate
processes. Python logic crosses the shell boundary through a formal CLI and
`argv`; embedded multi-line `python -c` is prohibited. Python, JSON, TOML and
Markdown are UTF-8. `tools/validation/check_text_compatibility.py` is the
authoritative byte/parser check. A missing writable validation temp surface is
reported as `not-observed`, not as product success. Both unified validation
entrypoints honor `TEMP_ROOT` so Windows and Unix can use an authorized short
temporary path without changing the repository checkout.

## 0.7 package architecture candidate (2026-07-24)

- Product role: DS Lite is a bounded research worker protocol for small and
  medium tasks. OpenScience remains responsible for global decomposition,
  resource scheduling, long-lived processes, and primary user interaction.
- The marketplace now targets six independent candidates. Core keeps the
  `deepscientist-lite` ID and nine skills at `0.8.1-beta.1`; Academic carries
  17 Nature skills at `0.8.1-beta.1`; Web, Knowledge, Empirical, and Engineering
  are `0.2.0-alpha.1` with one skill each.
- Core retains `ds-lite.graph.v2`, `ds-lite.evidence.v1`, work units,
  iteration, delegation, handoff, and Hooks. It has no vendor tree, MCP,
  daemon, database, academic bundle, or web backend and is constrained to 10
  MiB, 300 files, and nine discoverable skills.
- Optional packages publish `ds-lite.pack-compatibility.v1` and fail closed
  unless they observe Core `0.8.1-beta.1`. Marketplace dependency propagation
  is never assumed.
- Web v1 is public-only. `ds-lite.capability.v1` records observed backend
  support; `ds-lite.source-record.v2` is the write-side envelope while v1
  records remain readable. Every `fetch`, `search`, `render`, and `benchmark`
  invocation must declare one or more `--allowed-domain` values. The initial
  URL, every redirect, and every Firecrawl search result are checked against
  that scope; an empty scope or out-of-scope URL is a structured policy block.
  Login, cookie persistence, form submission, and user-profile reuse remain
  outside v1.
- Knowledge uses pending `ds-lite.knowledge-proposal.v1` records. Tapestry and
  ScholarAIO remain companion stores; DS Lite consumes explicit handoffs and
  never writes formal ResearchKB knowledge without a target-native review ref.
- Academic extends the existing `nature-response` route with original
  feasibility, atomic-concern, P0-P3 experiment, result-feedback, negative
  result, and resubmission gates. Rebuttal-Skill text is not copied because a
  repository-root license was not observed during planning.
- The frozen `plugins/deepscientist-lite/` `0.6.0-beta.1` monolith remains as
  historical evidence identity during the compatibility period. It is not the
  marketplace target, and no bulk cleanup is performed by the Agent.
- Source/package validation and the earlier four declared install matrices were
  deterministic checks only. Split-package real Hook behavior, real child
  delegation, the preregistered matched effect campaign, formal cache, fresh
  Desktop discovery, and release remain `not-verified` until independent fresh
  receipts pass. `ds-lite.formal-release-gate.v1` forbids adjacent-evidence
  inference.

## Historical 0.7.0-beta.2 academic and domain packs (2026-07-24)

- The current marketplace architecture supersedes this earlier four-package
  candidate with six independently installable packages: Core
  `0.8.1-beta.1`, Academic `0.8.1-beta.1`, Web and Knowledge
  `0.2.0-alpha.1`, plus Empirical and Engineering `0.2.0-alpha.1`. Core
  remains frozen; no Core Socratic mode is implemented before the real host
  gates close.
- Academic still exposes exactly 17 Nature skills. Its new protocols are
  `ds-lite.citation-check.v1`, `ds-lite.citation-check-batch.v1`,
  `ds-lite.revision-constraints.v1`, and `ds-lite.adversarial-review.v1`.
  Citation checks use four structured providers, cache only terminal statuses
  for 30/7 days, and block submission unless status is `verified`.
- Empirical exposes only `ds-lite-empirical` and validates
  `ds-lite.empirical-spec.v1` / `ds-lite.empirical-result.v1`. Engineering
  exposes only `ds-lite-engineering` and validates
  `ds-lite.engineering-analysis.v1`. Both previously required exact Core `0.7.0-beta.1`,
  fail closed, do not vendor runtimes, and target 150 files / 5 MiB.
- The earlier six deterministic installation matrices were `core-only`,
  `core+academic`, `core+empirical`, `core+engineering`,
  `core+web+knowledge`, and `all-six`. Source validation does not prove
  marketplace installation, fresh Desktop discovery, or any real host gate.
- Upstream comparison is recorded in
  `evaluation/cross-disciplinary-upstreams.json` with fixed commit, license,
  README/license hashes, design-atom classification, and clean-room or
  companion decision. No upstream prompt or repository is copied into the
  new packages. AI-Research and RDKit/Scanpy remain deferred candidates.
- Long-term user-facing boundaries are documented in
  `docs/maintainers/cross-disciplinary-adoption.zh.md` and
  `docs/user-guide.zh.md`; individual benchmark failures belong in evaluation
  receipts, not in this project memory.

## 0.8 release candidate boundaries (2026-07-24)

- Active marketplace packages target Core and Academic `0.8.1-beta.1`, and Web,
  Knowledge, Empirical, and Engineering `0.2.0-alpha.1`. The frozen
  `plugins/deepscientist-lite/` directory remains historical evidence only.
- Core now owns learning-receipt and quality-plan/result contracts. Learning is
  enforced at first side effect only when the host identifies an active skill;
  quality plans fail closed at PreToolUse and Stop when declared.
- Web writes `ds-lite.source-record.v2` through bounded public HTTP fetches while
  retaining v1 validation compatibility. Playwright, Firecrawl, and
  agent-browser remain capability-discovered external backends; Firecrawl
  search/render additionally require an API key and per-run authorization.
- Knowledge exposes doctor, external-export pull, proposal, withdraw, and
  supersede commands. Tapestry and ScholarAIO data stays outside the plugin;
  absent stable external exports remain `not-observed`.
- `ACKNOWLEDGMENTS.md` is the durable upstream index. Fixed commits, hashes,
  licenses, adoption depth, and exclusions remain in evaluation records.
- Source checks, package matrices, and local CLI checks do not unlock real
  provider, Hook, delegation, matched-effect, formal-cache, Desktop, OpenScience,
  or release gates. Each requires an independent receipt.
- Package validation covers the independent `core+web` and `core+knowledge`
  combinations in addition to the domain and all-six matrices. Optional packs
  fail closed when Core `0.8.1-beta.1` is absent or mismatched.
- The historical communication upstream matrix remains a fixed snapshot audit;
  two missing legacy local artifacts are reported as `not-observed`, while the
  active communication audit and Hook implementations are checked under
  `plugins/deepscientist-lite-core/`. Snapshot size/hash drift remains a blocker
  and must not be silently regenerated.

## 0.8 acceptance continuation boundaries (2026-07-26)

- Core Hook now includes the user-action gate contracts
  `ds-lite.user-action-request.v1`, `ds-lite.user-action-response.v1`, and
  `ds-lite.agent-action-resolution.v1`.
  Provider, browser, tmux/long-task, delegation, host, and release side effects
  require a matching one-shot user response; the response is consumed and cannot
  authorize a second action. When the agent itself verifiably repairs the exact
  blocker, it records a separate immutable resolution rather than forging a user
  response. Requests, responses, and resolutions exclude credentials, raw
  input/event streams, and absolute workstation paths.
- Trusted Hook, loop, cross-system, nature, and Web acceptance wrappers honor
  `TEMP_ROOT`; an unwritable root reports structured `not-observed` rather than
  silently using the repository cache. The split trusted fixture imports Core,
  not the frozen monolith.
- Communication audit, privilege-escalation blocking, Stop completion claims,
  and the unsupported-host installer response are part of the active Core Hook.
  Current source/offline evidence is recorded in
  `docs/maintainers/real-acceptance-audit-20260726.zh.md`.
- Existing host browser evidence proves public static HTML, a JavaScript-rendered
  iframe, and a public PDF can be read. RSS and a public Chinese article failed
  at network/host layers and have explicit failed source records. This is partial
  Web evidence, not a complete backend benchmark.
- The formal release gate remains blocked. Missing independent gates are pinned
  Codex/trusted Hook, real child delegation, verified external tmux owner and
  reconnect, matched effect, formal cache, fresh Desktop, Academic live providers,
  OpenScience fresh task, and post-release receipt. No commit, merge, tag, or
  release is authorized until those gates independently pass.

## 0.8 continuation notes (2026-07-27)

- Core Hook CLI output is ASCII-safe and decodes UTF-8 input explicitly so
  project paths containing Chinese characters remain routable on Windows.
- Learning receipt hashes cover the exact normalized summary file, preventing
  false stale results caused by the required trailing newline.
- Nature snapshot identity ignores generated Python bytecode caches; only
  pinned source/runtime files participate in drift checks.
- The complete repository regression is `411/411` passed in an authorized
  temporary root. This does not unlock any real-host or release gate.
- A fresh OpenScience task `wx-acp-codex-o9cq80xQ` completed a public-only
  Core+Web+Knowledge OpenAlex retrieval. It created a `ds-lite.source-record.v2`,
  an Evidence Pack, and a Science panel report; `ds_lite_evidence.py verify --strict`
  passed with HTTP 200 and five parsed records. This independently passes only
  the OpenScience gate. Provider, Hook, delegation, matched effect, formal cache,
  fresh Desktop, historical upstream snapshot drift, and release remain separate
  gates.

## 0.8.1 foreground autonomy boundary (2026-07-27)

- Active Core and Academic candidates are `0.8.1-beta.1`; optional package
  compatibility records fail closed unless they observe that exact Core version.
- `ds-lite.autonomy-contract.v1` is the release-scale foreground controller. It
  freezes goals and a gate DAG, records only sanitized progress/summary receipts,
  and makes automatic project advancement the default for an approved multi-gate
  project. A frozen gate never ends the controller while an independent gate is
  ready; it instead records its failure layer and moves to the next runnable gate.
- The contract defines continuity rather than relying on conversational prompting:
  three to six exponential-backoff retries are allowed only for declared,
  idempotent transient work; it performs bounded silent receipt polls after a
  command exits; and `--resume` reconstructs interrupted progress without
  replaying completed or frozen identities. Non-idempotent work remains frozen,
  never silently repeated.
- Every terminal gate writes a `ds-lite.progress-report.v1` with why it ran,
  what happened, evidence reference, failure layer, remaining progression, and
  next automatic action. This is a mandatory explanation and recovery record,
  not optional status prose.
- `ds-lite.loop-contract.v2` preserves the v1 shape and adds explicit bounded
  autonomy controls. `codex-autoresearch` is now a fixed-identity compatibility
  adapter: DS Lite owns the pinned Codex invocation and same-session resume so
  raw upstream event logs are not persisted.
- Hook context projects active autonomy state and grants the active contract
  ownership of conversation closure. While its summary is missing, unreadable,
  or non-terminal, UserPromptSubmit and PostToolUse project the current gate
  and the single `resume-autonomy-controller` action; Stop blocks phase/final
  closure and names the exact `run_autonomy --resume` continuation. Only a
  valid `completed` summary can release that conversation gate. This is a
  foreground control boundary, not a daemon, queue, implicit tmux owner, or
  permission bypass.
- An obsolete user-action request does not stall foreground autonomy after the
  agent has repaired its stated blocker: a `ds-lite.agent-action-resolution.v1`
  receipt closes only that request, preserves the original request unchanged,
  and does not grant authority for a second side effect.
- The complete repository regression reached `435/435` in the authorized
  temporary root. This remains source-level evidence and does not promote any
  blocked real-host or release gate.
- Offline/source validation does not prove real provider resume, matched effect,
  fresh cache/Desktop, Web/provider coverage, WSL owner/reconnect, or release.
- 2026-07-28 app-server fresh-task continuation used the validated
  `ds-lite.handoff.v1` digest
  `9695819bc5a0b056b34cccc77fa9a3806a66c9cc8f3436c2e2f0647de1d8aa71`.
  Fresh identity `appserver-continuation-20260728-03` observed Codex Desktop
  app-server initialize/thread/turn and `hooks/list`, but no DS Lite Hook event
  receipts and no autonomy summary. The gate is terminal
  `blocked / app-server-hook-not-observed`; it is not a Stop continuation pass.
  Fresh identity `appserver-continuation-20260728-04` added redacted
  app-server diagnostics: `hooks/list` returned four enabled plugin command
  hooks (`userPromptSubmit`, `preToolUse`, `postToolUse`, `stop`), all with
  `trustStatus=untrusted`; app-server emitted no `hook/started` or
  `hook/completed` notifications, wrote zero DS Lite Hook event receipts, and
  produced no autonomy summary. The current blocker is therefore the app-server
  Hook trust/invocation surface, before `Stop block`; release remains blocked.
  If a later fresh identity observes `Stop block + turn.completed` without a
  controller summary, classify it as
  `blocked / hook-continuation-not-observed`.
- The app-server continuation harness now trusts each fresh Hook through the
  official `config/batchWrite` `hooks.state` update and passes absolute event
  paths plus `DS_LITE_PLUGIN_ROOT` only to the child environment. The Hook
  projects its internal result to Codex 0.144.5's strict event-specific JSON
  envelope: `UserPromptSubmit` context is under
  `hookSpecificOutput.additionalContext`, while a Stop block uses only
  `decision: block` and a non-empty `reason`. Fresh identities `...-07` and
  `...-08` froze at fixture preconditions. `...-09` proved invocation but
  exposed the invalid former output shape. `...-10` observed a completed
  `UserPromptSubmit` Hook after the fix, then ended with a redacted non-retry
  app-server terminal error before Stop or an autonomy summary. The continuation
  gate remains `blocked / app-server-terminal`; no release evidence follows.
- The Stop Hook now executes one approved, foreground autonomy-controller
  resume when a contract remains active. A successful resume deliberately
  returns one Stop block for the summary turn; the next Stop allows only after
  the controller summary and active iteration are terminal. This was verified
  in `research/hook-autonomy-auto-20260728-02/`; it does not upgrade the
  separate app-server provider gate. Fresh
  `app-server-continuation-20260728-14` again proved formal Hook trust and
  UserPromptSubmit invocation, then froze as `blocked / app-server-terminal`
  before Stop because the provider response stream disconnected. The raw
  error was viewed only in memory under user authorization and is not recorded.
- Fresh app-server identities `...-15` and `...-16` repeated the trusted-Hook
  route with inherited proxy variables cleared and then `NO_PROXY=*` forced.
  Both still froze as `blocked / app-server-terminal` before Stop. This rules
  out the inherited proxy variables for those identities, but does not make a
  claim about all Windows transport layers.
- Rust control identity `rust-provider-20260728-02` made one actual pinned
  CLI request after correcting its `CODEX_HOME` path and froze as
  `blocked / fresh-cli-host`; the only retained observation is the normalized
  stream-disconnect class. Fresh identity `rust-provider-20260728-05` then
  revalidated the fixed binary and isolated non-secret route, forced direct
  egress, and ran one in-memory `reqwest/hyper/rustls` diagnostic. It exited
  before a JSONL terminal event or any allow-listed TLS, HTTP/2, proxy, DNS,
  reset, or stream-disconnect signal. Both receipts preserve zero raw output
  and zero raw error text. The root cause remains below the observable Rust
  CLI provider boundary, so app-server Stop continuation and release remain
  independently blocked.
- Formal cache identity `research/formal-cache-20260728-01/` passed without a
  model request: a new isolated `CODEX_HOME` registered the local marketplace,
  installed all six packages, and enumerated the exact expected package/version
  set through the pinned CLI. This closes only the formal-cache gate; it does
  not establish fresh Desktop discovery, a real provider turn, or release.
- Hook conversation control now takes controller ownership at
  `UserPromptSubmit` and `PostToolUse`, not only at Stop. An active approved
  contract is resumed in the foreground; a completed controller requires a
  terminal summary before closure, and Stop allows only after that summary.
  A contract may explicitly authorize a `continuation_command` and a separate
  receipt path so a frozen identity remains preserved while a fresh identity
  continues the approved gate. Local acceptance
  `research/hook-conversation-control-20260728-03/` proved
  `UserPromptSubmit -> controller completed -> summary required -> Stop allow`.
- Fresh real app-server identity `appserver-continuation-20260728-17` then
  observed the same chain with formal Hook trust: `UserPromptSubmit` completed,
  the controller summary became completed, `Stop` completed with `allow`, and
  the turn reached `turn/completed` without an error notification. The prior
  continuation harness receipt remains frozen as blocked only because it
  required the superseded Stop-first shape; the separate conversation-control
  receipt records the observed UserPrompt-first acceptance.

## 2026-07-28 Long-session control boundary

- `plugins/deepscientist-lite-core/scripts/ds_lite_autoresearch_runner.py` is the
  persistent session owner. It records a mutable job state plus append-only
  attempt and completion-failure receipts, preserves the observed session id,
  and invokes `codex exec resume` for the same session after an incomplete
  completion report.
- Core Hook `Stop` is a fail-closed decision surface. An active
  `research/autoresearch/job.json` causes the Hook to start a pending job with
  its frozen prompt/goals, or request same-session runner resume when state
  already exists, and return `controller_action=block-and-resume`; the Hook
  itself is not treated as proof that the host created a new turn. A child
  runner is guarded by `DS_LITE_AUTORESEARCH_CHILD` to prevent recursive Hook
  launches.
- Autonomy summaries may be resumed when blocked. Independent ready gates still
  run, retryable failures get fresh attempt receipt names, and auth,
  authorization, duplicate-risk, hook-trust, and user-action failures are
  represented as `awaiting_user_action` rather than silently retried.
- Completion requires all frozen goals and all required pre-release receipts;
  `post-release` is created only after the complete profile has allowed release
  and is checked as a separate closure condition. A Stop allow decision or a
  release claim must not be inferred from `Stop:block`, `turn/completed`,
  CLI/cache discovery, or a neighboring backend receipt.
- The runner owner lease is serialized through a persistent lock file and an
  owner token. Lease expiry may be reclaimed only while holding that lock, so
  two fresh runners cannot overwrite one another's active ownership record.
- `run_job` is one bounded foreground batch: an exhausted attempt budget writes
  `needs_resume` and keeps the session id. `watch_job` is the external
  autoresearch-style lifecycle owner; it repeatedly invokes the same job and
  `codex exec resume` until `completed`, `awaiting_user_action`, or an
  unrecoverable `failed` state. `max_batches` exists only for supervised tests
  and bounded operators, not as a completion shortcut.
- Autonomy resume never overwrites the first `summary.json`; later snapshots
  use fresh `summary-resume-###.json` names. A completed latest summary is
  idempotently returned instead of creating duplicate receipts. Each gate's
  progress receipt remains terminal and carries its failure layer, evidence
  reference, attempt count, retry observation, and next automatic action.
- The isolated memory diagnostic records only structured per-round
  `current_bytes`, `peak_bytes`, `current_delta_bytes`, and process peak bytes,
  plus aggregate hashes/metrics. It deliberately excludes prompt, stderr,
  environment, credentials, and raw event streams.
- Host control boundaries remain explicit: the Hook can block and invoke the
  DS Lite-owned runner, while only the external runner can create a new
  `codex exec resume` or app-server `turn/start`. Browser and computer-use
  tools are host execution surfaces and require their own observed receipts;
  their mere availability never proves DS Lite capability.
- The app-server acceptance harness now converts initialize/thread-start
  response-shape and transport failures into a redacted terminal
  `blocked/app-server-response-error` receipt. It records only the failing
  phase and structural counters; raw response text is never persisted. Fresh
  identity `appserver-continuation-20260728-33` exercised this path at
  `thread-start`; it remains blocked before any Stop event, so it cannot be
  relabeled as `hook-continuation-not-observed` or used for release.

## 0.8.1 continuation verification (2026-07-28)

- The Stop Hook now distinguishes a pending autoresearch job from an existing
  session. Pending `research/autoresearch/job.json` starts the DS Lite runner
  with its validated `initial_prompt` and `frozen_goals`; an existing state
  continues through the same-session `resume` path. Invalid pending metadata
  remains fail-closed. The regression is covered by the communication Hook
  suite.
- Fresh app-server identities `appserver-continuation-20260728-30` and `-31`
  were not release evidence. `-30` reached `turn/completed` with only
  `user-prompt-submit:allow` and `stop:allow`, so no Stop block occurred.
  `-31` observed only `user-prompt-submit:allow`, one redacted error category,
  and no Stop event. Both remain `blocked/app-server-terminal`; neither is
  relabeled `hook-continuation-not-observed` because the required Stop block
  plus terminal event was not observed.
- The fresh memory receipt `research/artifacts/memory-diagnostic-20260728-resume-04.json`
  passed with structured per-round memory samples and no raw input/output
  persistence. The strict aggregate
  `research/artifacts/formal-release-gate-20260728-resume-05.json` remains
  blocked: provider, app-server continuation, and Web are nonpassing, while
  source, offline, CLI, Hook, matched effect, fresh Desktop, docs, and
  OpenScience have no independent passing receipt. No post-release receipt
  exists and no release action is permitted.
- Independent verification after this change completed `477/477` unittest,
  repository validation, all six package checks and eight installation
  matrices, PowerShell/Bash syntax, full source/test `py_compile`, cross-system
  validation, and `git diff --check`. The official aggregate wrapper was also
  run separately but timed out after about 304 seconds without a terminal
  result; that timeout is not treated as a pass.

## 0.8.1 runner hardening follow-up (2026-07-28)

- The persistent runner now fails closed when an incomplete first attempt does
  not expose a session id. It writes `session-id-not-observed` and never
  starts a new session under the same job identity. Invalid or drifting ids
  are likewise terminal failures.
- Completion-failure receipts retain a structured
  `completion_failure_prompt`, while `last-message.txt`, `events.jsonl`, and
  memory receipts retain only bounded summaries, hashes, and numeric metrics.
  Mutable `meta.json` state records the owner token and allowed lifecycle
  states; attempt and summary receipts remain write-once.
- The lease is extended beyond the configured child-process timeout so an
  active bounded child cannot be claimed by a second runner during execution.
  `needs_resume` remains a scheduling state, never a completion state.
- Focused follow-up verification passed runner `10/10`, memory diagnostic
  `1/1`, app-server protocol `8/8`, communication Hook `24/24`, and targeted
  Python compilation. These are source-level and protocol-level checks only;
  they do not promote the frozen real-host, provider, Web, Desktop, matched
  effect, or release gates.
- The Hook now defaults active autoresearch jobs to the persistent `watch`
  runner mode. This mirrors the vendor `runLoop` boundary: the runner owns
  `codex exec` followed by same-session `codex exec resume` until the completion
  report is valid or a user-action/non-retryable blocker is terminal. The
  explicit `runner_mode=bounded` option remains only for supervised tests;
  `Stop:block` is still not treated as observed continuation unless a fresh
  turn and terminal summary are recorded by the host.
- Python tests must be launched through `tests/run_tests.ps1` or
  `tests/run_tests.sh`. Each launcher allocates a new run directory below the
  project-volume `research/.validation-tmp` and sets
  `TEMP`, `TMP`, `TEMP_ROOT`, `DS_LITE_TEST_ROOT`, and an isolated pycache
  prefix. This avoids the system `C:\...\Temp` surface and never removes or
  overwrites prior test artifacts.
- `evaluate_stop_first()` now rejects any receipt that observes
  `Stop:block + turn/completed` without an explicit same-session continuation,
  even when a summary file already exists. The required failure layer is
  `blocked/hook-continuation-not-observed`; summary presence cannot substitute
  for a new turn.
- Fresh project-volume identity `research/appserver-continuation-20260728-40/`
  completed preparation and fixture setup, then observed a real app-server
  `UserPromptSubmit` Hook and a terminal provider error before Stop. Its receipt
  remains blocked and is not promoted to Stop-first evidence. Identity `-39`
  was preserved as an incomplete preparation attempt; neither identity is
  retried or overwritten.

## Project-volume temporary directory policy (2026-07-28)

- Validation launchers and Hook-owned autonomy/autoresearch child processes use
  `research/.validation-tmp` by default. An explicit `TEMP_ROOT` is accepted
  only when it is this directory or one of its children; system-volume and
  repository-external temporary roots are rejected.
  They set `TEMP`, `TMP`, `TEMP_ROOT`, and an isolated `PYTHONPYCACHEPREFIX`
  before starting child work, so validation scratch files do not default to the
  system `C:` temporary directory.
- Existing temporary directories and receipts are retained. Cleanup is not part
  of validation, and a new identity is required for every retry.

## 0.8.1 external recovery policy (2026-07-29)

- `ds_lite_recovery.py` is the shared redacted classification boundary for the
  autonomy controller, persistent runner, and app-server acceptance harness.
  HTTP 408/429/500/502/503/504 and transport interruption are retryable;
  401/402/403, quota, payment, and authorization are
  `awaiting-user-action`; malformed protocol, session drift, missing session
  ids, owner conflicts, and Hook trust failures freeze the identity. Unknown
  external failures receive one bounded diagnostic/retry classification rather
  than being silently labeled network failures.
- Attempt and gate receipts retain only recovery class, normalized failure
  layer, status-code class when available, delay/next-retry metadata, hashes,
  and next action. They never retain raw provider text, prompt, environment,
  credentials, or event streams. A later explicit checkpoint request resumes a
  persisted recoverable same-session job; it never converts a lost session into
  an unrecorded new session.
- A runner or provider blocker freezes only that identity. The autonomy DAG
  continues unrelated ready gates, while the complete release profile remains
  fail-closed until every independent receipt and post-release verification is
  passed.

## Stop-first host boundary (2026-07-29)

- The explicit `ds-lite.stop-first-protocol.v1` marker is restricted to an
  isolated acceptance workspace. It prevents the UserPrompt hook from running
  the controller before the first Stop, so the host must observe `Stop:block`.
  Only then may the external harness run the controller and submit a second
  turn on the same app-server thread; a later `Stop:allow` is accepted only
  with the completed controller summary and that observed continuation.
- App-server stdout is consumed by a queue-backed deadline reader. A silent
  host must produce a redacted terminal timeout receipt rather than leave the
  acceptance process blocked in `readline()`. This behavior is covered by the
  focused Hook and app-server regression suites.

## DS Lite 控制面 Spike（2026-07-31）

- Phase 0 将 Hook 收束为当前 turn 的状态投影、guardrail、交付检查与一次同 turn repair 请求；它不拥有持续调度、网络退避或跨会话所有权。遗留 Stop-first 外部第二个 `turn/start` 验收器已退休为永不通过的历史诊断。
- 控制面验收固定使用仓库内隔离取得并核验的 `codex-cli 0.128.0`；当前 Desktop 自带 binary 已漂移到更新版本，不能混用。Core 内保存了 0.128.0 生成的 app-server schema；其 `SHA256SUMS` 摘要为 `9e22b7c4174cdaa87fc3240bce6bfecf8855f263eddfed3e97e49cb165527afb`，doctor 必须现场计算，不能用期望常量自证。
- Phase 0.5 的最小控制面把 DS Lite domain truth（action/outbox/workflow binding/lease/fencing）与 DBOS durable-runtime 候选分开。桥接不变量是 `action_id == workflow_id`，并且 canonical thread 缺失或 response gap 必须归类为 ambiguous，禁止隐式新建 thread。
- 固定种子 fake-host K1-K6 与 Windows 资源数据已生成，但这不能替代真实 app-server/Hook 或 DBOS durable backend。`research/artifacts/control-plane-phase0.5-20260731/spike-decision-02.json` 的当前结论是 no-go、`release_allowed=false`；后续只可在可信真实宿主具备时重跑最小 lifecycle 和 Hook receipt，再生成新 decision，不得用 fake 解除 release gate。
