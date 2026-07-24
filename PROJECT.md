# DeepScientist Lite Codex Plugin

## Cross-system execution rule

Executable wrappers are ASCII-only and pass paths and prompts through argv to
formal Python CLIs. Run `teaching/run_cross_system_validation.ps1` or the Bash
equivalent for encoding, format, shell syntax, and argv checks.

## 研究背景

本仓库实现一个面向教学、快速启动和小型科研项目的轻量 Codex 插件。它抽取 DeepScientist 工作流中可恢复、可审计、可教学的文件协议，不复制 daemon、Web/TUI、connector、MCP 或长期调度平台。

根目录 `PROJECT.md` 是本仓库的长期项目记忆；`plugins/deepscientist-lite/assets/templates/PROJECT.md` 是插件为用户项目生成的合同模板，两者职责不同。

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

1. 通过九个 `ds-lite-*` skills 作为核心层，再加十七个 `nature-*` 功能 skill 读取项目合同、状态、文献与证据，共 26 个可发现入口；`$ds-lite` 只解释介入理由并路由到一个动作 skill。
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
- `plugins/deepscientist-lite/hooks/` 与 `scripts/ds_lite_hook.py`：可选轻量 Hook 配置和脱敏 helper；fresh-host 加载仍未验证。
- `tests/`：Graph v2、CLI、迁移、并发和路径回归测试。
- `tools/validation/`：仓库级验证器与 shell/PowerShell 入口。
- `docs/`：设计、迁移、已知问题和发布维护资料。
- `teaching/`：不进入运行时包的课程与演示材料。
- `teaching/lab_runner.py`：跨平台课程准备器；七个协议 lab 支持 student/reference，matched pilot 只生成隔离 student workspaces 与独立教师材料，不预写模型结果。
- `teaching/pilot_runtime.py`：授权后的 matched pilot 冻结、双 home 隔离、preflight/单次 canary、18 次串行执行、脱敏 receipt 和 fail-closed resume。
- `teaching/pilot_score.py`：只读公开产物的自动评分与 incomplete/待盲评报告；不读取完整会话或隐藏推理。

## 运行流程

- Unix-like：`bash tools/validation/run_validate.sh`
- PowerShell：`powershell -ExecutionPolicy Bypass -File tools/validation/run_validate.ps1`
- 单元测试：`python -m unittest discover -s tests -v`
- 仓库 smoke：`python tools/validation/validate_repo.py`
- 教学课程：`python teaching/lab_runner.py --lab quickstart --mode student --output <path>`
- 行动与反思：`python teaching/lab_runner.py --lab action-reflection --mode student --output <path>`
- 对照 pilot：`python teaching/lab_runner.py --lab matched-pilot --mode student --output <path>`
- 真实 pilot：`powershell -File teaching/run_pilot.ps1 -Action prepare|install|preflight|canary|run|resume|score`，或 `bash teaching/run_pilot.sh <action>`；关键路径、pilot ID、授权引用和 CLI 必须显式提供。`install` 只建立隔离 skill home，不是 cache 安装；失败/超时/ambiguous 不能用 resume 重试。

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
- Hook helper 覆盖非工作区放行、脱敏状态附着、Graph 直改/危险命令/tmux 扩容阻断、合法 CLI 放行和 Stop 单次续跑；Hook fresh-host 加载保持 `not-verified`。
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
- 已发布 v0.4 不加入 daemon、MCP、Web/TUI、hooks 或长期后台调度；未发布 v0.5 只增加插件局部、无状态的 Hook helper，且不在 manifest 声明，宿主加载未验证。OpenScience 可作为上层主管调用 DS Lite worker，但 DS Lite 只提供文件化任务板、证据门和单轮迭代协议。
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

The fresh Loop acceptance receipt `.validation-tmp/offline-loop-acceptance-20260723-final/offline-loop-acceptance.json` records fake `partial -> completed` continuation as passed and `codex-autoresearch` as `blocked-not-verified` with zero external process spawn. It is offline protocol evidence only and does not unlock any real host or release gate.

## Current upstream integration status (2026-07-24)

- The plugin candidate is `0.6.0-beta.1`. It exposes the nine DS Lite core skills plus the complete 17-skill `nature-skills` snapshot at commit `91862221b39f7ca16d52ae0e1e9cb6c2bb31a96b`; `nature-shared` remains an internal, non-discoverable layer.
- Nature integrations are opt-in. `ds_lite_nature_setup.py inventory|doctor|onboarding|apply|verify` checks local tools and environment-key presence, writes only workspace-local `.ds-lite/nature/` files, and never changes global Codex, credential, marketplace, or MCP configuration.
- `codex-autoresearch` is an authorized fixed snapshot at commit `f2389bffbb4cd7789deb6796bc4ba35bf31f2a90` / npm `0.1.5-beta.0`. The adapter preserves bounded goals, completion evidence, zero retry, and fail-closed stopping, but does not execute the upstream CLI until a redacted child-output contract is supplied.
- `tools/validation/upstream_manager.py` inventories every registered upstream, verifies local provenance, and produces read-only update plans. It never overwrites vendor sources or auto-publishes changes.
- Nature skill `source_skill_sha256` values hash UTF-8 text after normalizing line endings to LF. Other vendored files retain byte-for-byte hashes, so provenance remains stable across Windows and Unix checkouts without weakening snapshot validation.
- Offline integration, onboarding, adapter, loop, text-compatibility, cross-system, and repository validation are source-level evidence only. Real provider, Hook host, Desktop, child delegation, matched effect, formal cache, and release gates remain locked.
- On 2026-07-24 the unified Windows validation entry completed `304/304` unittest cases, repository validation, PowerShell syntax checks, `py_compile`, and `git diff --check`. The fresh cross-system receipt observed 827 files with zero failures; Bash, PowerShell 7, and shellcheck were `not-observed` on this host.

Executable entrypoints (`.ps1`, `.sh`, `.cmd`) are ASCII and only orchestrate
processes. Python logic crosses the shell boundary through a formal CLI and
`argv`; embedded multi-line `python -c` is prohibited. Python, JSON, TOML and
Markdown are UTF-8. `tools/validation/check_text_compatibility.py` is the
authoritative byte/parser check. A missing writable validation temp surface is
reported as `not-observed`, not as product success.
