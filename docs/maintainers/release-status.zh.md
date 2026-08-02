# Product Positioning And Long-Term Memory

## 2026-07-24 候选整合状态

当前源码候选为 `0.6.0-beta.1`，包含 9 个 DS Lite 核心 skill 和固定
commit `91862221b39f7ca16d52ae0e1e9cb6c2bb31a96b` 的 17 个 `nature-skills`
功能 skill，共 26 个可发现入口（历史单体口径）。当前 marketplace 改为 Core 9、Academic 17 和四个各 1 入口的可选包；`nature-shared` 只作为 vendor 内部共享层，
不计入用户 skill。Nature 的 MCP/API、浏览器、下载、LaTeX、Node/Python 依赖
通过 `ds_lite_nature_setup.py` 做工作区级首次配置引导，不修改全局 Codex 或
凭据。

`codex-autoresearch` 已按作者授权纳入固定快照
`f2389bffbb4cd7789deb6796bc4ba35bf31f2a90`（npm `0.1.5-beta.0`），但 DS Lite
adapter 仍保持 bounded、零自动重试和 fail-closed；在脱敏 child-output 协议
验证前不会启动上游 runner。`upstream_manager.py` 只做来源、版本、许可证和
差异审计，不自动覆盖或发布。

本轮离线测试与仓库验证通过只说明源码、入口、快照 provenance、配置引导和协议
边界成立。真实 provider、完整 Hook host、Desktop task、真实 delegation、
matched effect、formal cache 和 release gate 仍为 `not-verified`。

2026-07-24 的统一 Windows 验收实际运行 `298/298` unittest，并通过 repository
validator、PowerShell 5.1 语法检查、`py_compile` 和 `git diff --check`。跨系统
报告为 `passed`，扫描 1465 个文件且编码/格式失败为 0；Bash、PowerShell 7 和
shellcheck 在当前执行面不可用，均记录为 `not-observed`。证据：
`.validation-tmp/validation-20260724T0120359466120-21292/cross-system-validation-20260724T0120359466120-21292.json`。

> 当前 0.8 候选以六包 marketplace 结构为准：Core/Academic `0.8.1-beta.1`，Web/Knowledge/Empirical/Engineering `0.2.0-alpha.1`。下文早期 `0.6.0-beta.1` 记录保留为历史证据，不代表当前安装边界。

## 2026-07-25 本轮源码进展

Web CLI 已把域名范围从文档约定提升为执行门：`fetch`、`search`、`render`、
`benchmark` 都要求重复传入 `--allowed-domain`；初始 URL、重定向和
Firecrawl 搜索结果逐一复核，缺失或越界均返回 `policy/blocked`。新增的
provider mock 覆盖成功渲染、越界结果、429、超时和非法 JSON，密钥不会进入
source record 或错误信息。Web 专用验证入口已纳入协议测试和 `py_compile`。

九个 Core skill 的文字层回归已通过：每个入口都明确要求保护内容原样保留，
Core runtime notice 不暴露内部 upstream 快照路径。六包矩阵、包体积、兼容性、
Web/Empirical/Engineering doctor、通信层测试和 `git diff --check` 通过。

当前执行面仍无法写入系统 Temp 或仓库 `.validation-tmp`，因此完整 unittest、
学习/质量集成测试和需要产物目录的 CLI 测试只能记录为 `not-observed`，不能升级
为失败。Knowledge doctor 未发现 Tapestry/ScholarAIO 外部 CLI；真实 provider、
四类 Hook、delegation、matched effect、formal cache、fresh Desktop、OpenScience
和 release 继续保持 `not-verified/blocked`，不得发布。

## 2026-07-24 最新真实门

`communication-beta2-20260724-wire-01` 的单次 Responses wire 请求通过：terminal
event、非零 usage=4412、output=true、request_count=1、automatic_retry=false。
随后 fresh `communication-beta2-20260724-gated-cli-02` 的 pinned Codex 0.144.5
CLI canary 通过：turn.completed、最终反馈、16 个工具事件、usage=77706、工作区
未修改、acceptance gate=passed。首次新 Hook host 在启动前被 provider trust
policy 阻断，原因是外发目的地尚未被明确批准；没有重试或绕过。Hook 四类事件、
Desktop、真实 delegation、matched effect、formal cache 和 release gate 继续
保持 `blocked / not-verified`。

## Primary Work

DeepScientist Lite is a Codex plugin project. Its primary goal is to make the core DeepScientist research protocol teachable and usable without deploying the full DeepScientist platform.

The plugin is the main product. Teaching cases and small experiments are validation material, not the product itself.

## What Counts As Plugin Progress

- Skills are discoverable, triggerable, and concise.
- The file protocol is easy to initialize in a new or existing research project.
- `ds_lite_state.py` keeps state traceable without hidden chain-of-thought.
- Users can recover from install/cache/encoding failures.
- A teacher can explain the core workflow in 20-30 minutes and run evidence/review labs in 45 or 90 minutes.
- A student can run a one-stop project loop and inspect the route afterward.

## What Experiments Are For

Experiments validate whether the plugin helps preserve research state, failures, and claims. They can be used as teaching demos, but they should not redefine the plugin as an algorithm benchmark repository.

The sanitized paradigm-comparison teaching case demonstrates how DS Lite records a real route: source audit, idea choice, experiment result, negative evidence, and next-step reasoning.

## Current Release Judgment

`v0.4.0-beta.2` is the worker-protocol source/package beta. It keeps Graph v2 and Evidence Pack v1, adds Mission Board projections, `mission` / `render-status`, a seventh `$ds-lite-iterate` skill, and OpenScience worker handoff guidance. Source/package validation is release evidence; fresh cache installation, all seven skills in a new thread, and one installed bounded iterate checkpoint remain explicitly unverified.

P0 source validation covers `ds-lite.work-unit.v1`, typed Evidence Pack promotion, `ds-lite.review-result.v1`, claim readiness, evidence detail, and route-scoped waiting. This remains source/package evidence only: the installed cache remains unverified and must not be inferred from the source tree. P1 action/receipt and P2 typed external-long profile are not part of this P0 claim.

The unreleased v0.5 source branch adds a domain-neutral `ds-lite.factor-card.v1`, `$ds-lite-coordinate`, and a ninth `$ds-lite` gateway. It also adds a minimal `ds-lite.iteration.v1`, a derived hypothesis pool, a shared responsible-exploration covenant, plugin-local Hook helpers, and redacted pilot progress. Their schemas, templates, CLI validation, negative fixtures, skill metadata, and repository anchors are source-testable. Fresh-agent Factor Card behavior, implicit trigger behavior, real child-task dispatch, host-enforced path scope, Hook loading, and new-thread nine-skill discovery remain not verified until separately authorized acceptance runs are recorded.

The same source branch now prepares and operates a 4-case x 3-arm matched-control teaching package. The runner creates equal inputs and staged prompts; the first authorized runtime froze an eight-skill source identity, created zero-skill control and DS Lite homes, serialized 18 calls, reduced JSON events without retaining raw streams, failed closed on uncertainty, and auto-scored only public artifacts pending blind review. That frozen run stopped on the initial plain engineering process at `0/18`, with zero tokens and no result. It remains permanently blocked and is not rewritten to the current nine-skill source. This is useful stop-boundary evidence, not an arm comparison, cost result, reserved-profile validation, or `0.5.0-beta.1` release evidence.

The current acceptance path separates `prepare`, isolated-skill-home `install`, model-free `preflight`, and one-shot implicit `canary`. Preflight checks the pinned CLI, an authentication category, feature enumeration, zero/nine skill separation, WSL, and frozen source identity while persisting only redacted summaries. The canary is read-only and ephemeral, rejects duplicate receipts, and cannot authorize trigger, Hook, pilot, delegation, cache, or release gates. An isolated home is not a formal plugin-cache installation.

The 2026-07-18 E1 run passed preflight with Codex CLI `0.144.5`, an environment API-key category, stable hooks/plugins/multi-agent feature listings, zero/nine skill prompt separation, WSL, and a matching source digest. Its only implicit canary established a thread, then finalized as `timeout` with a redacted `rate-limit` diagnostic, zero tokens/tools, no terminal turn or feedback, and no workspace change. Finalization took 378.098 seconds because the old Windows `.cmd` cleanup left child pipes open until the exact canary process tree was stopped. The pilot is frozen and did not enter E2. The cleanup bug now has a deterministic red-green regression test; the request was not replayed and the receipt was not manually rewritten.

The 2026-07-20 slim isolated-home test used two minimal `CODEX_HOME` trees: `control-slim` with zero DS Lite skills and `ds-lite-slim` with the current dirty-source acceptance package exposing nine skills. Both homes shared the same pinned Codex CLI `0.144.5`, model `gpt-5.6-sol/low`, copied authentication, and read-only ephemeral canary workspace. Preflight confirmed model, config, auth, provider reachability, and zero/nine skill separation; `doctor` overall remained `fail` only because the pinned test CLI is not the global npm install. The control canary, DS Lite canary, and `$ds-lite-iterate` fail-closed canary all exited 0 with `thread.started`, `turn.completed`, final output, usage, and no workspace writes. This verifies only the slim isolated plugin effect: DS Lite gave clearer applicability, state-checking, and blocked-report behavior at higher token/time cost. Formal cache installation, fresh Desktop host discovery, Hook host loading, full skill campaign, matched A/B, delegation, tag, push, and release readiness remain unverified.

The next acceptance layer separates cross-task performance from explainability. Deterministic scoring and state/delegation protocol tests now pass, but no new 12-case real model comparison or real subagent dispatch has been run in this cycle. Until those isolated probes produce fresh receipts, report the source protocol as verified and cross-task expression/host delegation as not verified.

The corrected 2026-07-20 isolated preflight passed, but its single implicit canary for `cross-task-explainability-20260720-02` froze at the 180-second gate with a redacted `rate-limit` category, zero usage/tools, no terminal turn or final feedback, and no workspace change. This is an external availability failure for this attempt, not evidence of plugin success or failure. The receipt remains immutable; no automatic retry, 12-case campaign, or delegation probe followed.

本轮沟通增强的确定性验收已完成：Windows PowerShell 与 Bash 入口均运行 169 个单元测试并通过，仓库 validator、`py_compile` 通过；WSL `DS-Lite-Ubuntu-24.04` 完成运行时编译和 10 个触发契约测试。WSL 的 `E:\\PyCharm 2025.2\\bin` 路径转换警告属于宿主环境噪声。该证据只说明源码协议、Windows/Bash/WSL 的标准库兼容性和强制反馈规则成立，不等同于真实 Agent 表达、Hook 宿主加载、正式 cache 或发布验收。

2026-07-20 provider 隔离配置回归已修复并通过 35 项 `test_pilot_runtime.py`：control 与 DS Lite 隔离 home 现在各自复制正式 home 的非敏感 custom provider 路由和相对 model catalog；认证文件、token、header 与全局配置不会复制。此前“模型可解析但真实请求 provider 不可用”的现象是隔离配置不完整导致的设置缺口，不是模型名称解析成功的证明。该修复只影响未来新 pilot 的准备阶段，不能重放或改写已经因 `rate-limit` 冻结的 canary。

新的 `communication-beta2-20260720-gated-02` 已完成一次全新验收：provider route/catalog 均显示 `copied`，preflight 通过，真实 canary 建立 thread 后以 `transport` 失败（`turn.completed=false`、无工具、无 final feedback、usage=0），统一审计门为 `blocked`。因此当前结论是“隔离配置已验证，provider 运行时 transport 仍未验证”，不启动 delegation、matched comparison、正式 cache 或发布门。

统一验收审计门已经加入 pilot receipt 的 `extensions.acceptance_gate`。`communication-beta2-20260720-gated-02` 的 source/environment/authorization 和隔离 cachebuster package 门通过；唯一真实 canary 在 `transport` 失败前没有 final feedback、tool、turn terminal 或 usage，因此 C4 为 `blocked`。按门禁规则，Hook host、matched comparison 和真实 delegation 没有启动，不能写成插件效果通过。

真实表达验收的截断原因必须按层报告：gated-02 canary 已建立 thread，但在产生 turn terminal、final feedback、tool observation 和 usage 前以 `transport` 结束，因此没有可评分的 Agent 输出。现有 receipt 不足以区分认证拒绝、网络不可达、协议错误或子进程/管道问题。插件不能从零输出推断表达改善；下一次必须使用新 pilot id，在单独确认 provider 可用后重新执行一次 canary，失败仍冻结，不得重放原请求。

2026-07-20 新增 `ds-lite.transport-diagnostic.v1` 和 fresh-only 离线验收。隔离 home 强制 `request_max_retries=0`；本地 fake provider + fake Codex 对 success、auth、rate-limit、network、malformed response、child early exit 和 ambiguous 七个场景各启动一次，除 early exit 为零次 HTTP 请求外其余均为一次，未保存 raw stderr。Hook、delegation 和 matched comparison 分别只获得 `fake-host-tested`、`protocol-tested` 与 `prepared-and-freeze-tested`，报告固定 `real_gates_unlocked=false`。真实 provider、Codex wire compatibility、Hook loading、child dispatch、matched effect、formal cache 和 Agent 表达仍未验证。

该层新增后的 PowerShell 与 Bash 统一验证入口均运行 189 项测试并通过，仓库 validator 与清单内 `py_compile` 整体退出码为 0；Bash 入口有 1 项按平台条件跳过。证据仍仅覆盖源码、fake transport 和离线协议，不提升任何真实宿主或发布结论。

2026-07-21 真实 wire 诊断已运行两个 fresh 身份：`communication-beta2-20260720-wire-diagnostic-01` 和修正归约器后的 `communication-beta2-20260720-wire-diagnostic-02`。两者均通过 prepare、preflight、固定 Codex `0.144.5` SHA 校验、环境 key 类别、route fidelity、零重试和 DNS/TCP/TLS 探针；authenticated minimal Responses SSE 均只发起一次 provider 请求并冻结。`wire-diagnostic-02` 的脱敏 receipt 显示 `http_status_category=4xx`、连接已建立、响应头已收到、无 terminal event、usage=0、无自动重试，修正后的失败层为 `protocol`。因此本轮没有创建 `gated-03`，也没有启动 CLI canary、真实 Hook host、真实 delegation、matched effect、formal cache 或发布门。

本轮修改后重新运行完整 unittest：205 项通过；仓库 validator 通过；`git diff --check` 退出码为 0，仅报告既有 CRLF/LF 规范化警告。当前 release 状态保持未发布，真实阻塞点收窄为 configured Responses route 的 provider/model/parameter acceptance，而不是本地 DNS/TCP/TLS 或隔离配置遗漏。

后续 fresh 身份已补充如下：`communication-beta2-20260720-wire-diagnostic-03` 的 Responses 探针收到 HTTP 200、terminal event 和非零 usage，证明 provider 级 Responses wire 兼容。`communication-beta2-20260720-gated-03` 的单次 CLI canary 仍为认证 4xx 并冻结；修复隔离 route 的非敏感 `env_key=OPENAI_API_KEY` 后，新身份 `communication-beta2-20260720-gated-04` 的 CLI canary 通过，观察到 `turn.completed`、最终反馈、14 个工具事件和非零 usage。随后 `communication-beta2-20260720-host-01` 在隔离 CODEX_HOME 中通过真实 marketplace/add 安装候选版本、九个技能和 Hook manifest，但全新 CLI 任务没有产生 JSONL 事件，宿主门冻结。故真实 Hook loading、Desktop fresh task、真实 delegation、matched effect、formal cache 和 release gate 仍未验证。

2026-07-22 新增 `ds-lite.handoff.v1` 与 `ds-lite.cli-compatibility.v1`。前者用于长对话、resume 和 child-task 交接，要求 digest、授权边界、权威配置、相对证据引用和唯一下一步；后者把 PowerShell、cmd、Git Bash、WSL/Linux Bash 和 external host 视为不同执行面，显式归约引号、转义、编码、PATH、WSL 路径、`.cmd` 子进程和管道状态。两者都是脱敏协议，不改变真实宿主门状态。

同日新增 `fresh_host_probe` 并运行全新 `communication-beta2-20260720-host-02`：marketplace 安装通过，单次真实 CLI probe 启动并退出，stdout/stderr 均关闭，无 timeout，但产生 0 个 JSONL/terminal event，失败分类为 `unknown`，不重试并冻结。该证据排除了本次管道未关闭和超时终态问题，但不能说明具体 provider/CLI 错误，也不能解锁 Hook、delegation、matched 或 release gate。

随后创建全新 `communication-beta2-20260720-host-03`，只执行无模型的 `--version`、`features list` 和 `plugin list --json`。三个进程均启动、返回码可见且 stdout/stderr 关闭；receipt 明确未发起外部模型请求，故仅证明 CLI-start 边界。Hook loading、Desktop task、真实 delegation、matched effect、formal cache 和 release gate 仍未验证。

在此基础上，新建 `communication-beta2-20260720-host-04`，使用已校验的 Codex `0.144.5`（SHA-256 `EFDB3540EF74B9909408C8D38DA79483454797B36F471E3E004FC2BF2B70E22A`）重复三个无模型命令。三个进程均启动、退出状态可见且管道关闭；版本字段归一化为 `0.144.5`。这只通过 pinned CLI-start 门，尚未验证候选插件安装、Hook、Desktop、delegation、matched effect、formal cache 或 release gate。

随后创建全新 `communication-beta2-20260720-host-05`，在隔离 marketplace 中安装候选 `0.5.0-beta.1`，观察到九个技能和 `hooks/hooks.json`。一次 pinned CLI 任务以退出码 2 结束，未产生任何四类 Hook 事件 receipt；原始输出未保存，不重试并冻结。故 Hook loading、Desktop task、delegation、matched effect、formal cache 和 release gate 仍未验证。

静态读取 pinned `0.144.5` 的 `exec --help` 后确认，旧 probe 使用了不支持的 `--ask-for-approval`，且缺少 `--skip-git-repo-check`；wrapper 已修正，没有重放 host-05。新 host-06 重新安装候选并执行一次真实任务，产生了 `UserPromptSubmit` receipt，随后超时，未产生 PreToolUse、PostToolUse 或 Stop。故只能确认 Hook loader 的部分调用，完整 Hook 验收仍失败并冻结。

host-07 进一步验证了 route TOML 必须位于 marketplace/plugin 表之前；修正根级配置后，pinned model-free CLI、候选安装、九个技能和 Hook manifest 均通过。真实 provider 任务未启动，因为当前执行策略拒绝向未明确可信的外部目的地发送工作区上下文；这不是产品通过，也不是产品失败。真实 Hook、Desktop、delegation、matched effect、formal cache 和 release gate 仍未验证。

离线验收 `offline-acceptance-20260722-host-boundary` 已通过 fake transport、fake Hook、delegation protocol 和 matched 准备/冻结检查；报告明确保持真实 provider、真实宿主、真实子智能体、效果测量和 release gate 锁定。

The manual tmux capacity handshake remains pending release evidence until a user-created fixed-socket surface survives a real disconnect/reconnect probe, a missing socket causes a clean stop without `new-session`, and a pane-scoped Codex CLI child worker records provider query/resume evidence separately from tmux and experiment recovery.

The previous `v0.3.0-beta.1` evidence-review teaching beta remains useful historical evidence: on 2026-07-05, 36 local tests, the repository smoke, Windows PowerShell, Git Bash, the plugin validator, and all six v0.3 skill validators passed. That evidence does not prove v0.4 cache installation or `$ds-lite-iterate` behavior. See the [hardening log](v0.3-hardening-log.zh.md) and [Codex acceptance audit](v0.3-codex-acceptance.zh.md). Remote CI for the new commits, explicit cache installation, completion of the main review/analysis/iterate recovery route, independent teaching reports, macOS verification, and repeatable cache-upgrade recovery remain release evidence.

## Long-Term Memory Rules

## 2026-07-23 真实 Hook host 状态

`communication-beta2-20260723-gated-cli-01` 已通过单次 pinned CLI canary，`loop-wire-05` 已通过 Responses provider wire gate。随后 fresh Hook host `trusted-hook-02` 和 `trusted-hook-03` 观察到四类事件但全部为 `allow`；`trusted-hook-04` 在 fixture 准备阶段因 action kind 未注册而冻结；`trusted-hook-05` 在有效 running-iteration fixture 上观察到 UserPromptSubmit、PreToolUse、PostToolUse，但任务以 `turn.failed` 终止，未观察到 PreToolUse block 或 Stop block/allow 序列。因此 Hook host 仅为 partial loader evidence，真实 delegation、matched effect、formal cache、fresh Desktop 和 release gate 仍未验证。完整 unittest 实际为 `289/289`，跨系统报告为 `passed`，缺少的宿主工具保持 `not-observed`。详见 `docs/maintainers/real-hook-acceptance-20260723.zh.md`。

该段 supersede 了本文件中较早的“尚未创建 CLI canary”临时口径：后续 fresh 身份已经完成 wire-05 和 gated-cli-01，但不改变旧 receipt，也不解锁后续真实门。

- Keep durable plugin decisions in this file, `known-issues.md`, `release-checklist.md`, README, and case studies.
- Keep algorithm experiment details inside the case study or the host research project.
- Do not add MCP, daemon, Web/TUI, stateful Hook ownership, or background scheduling. Plugin-local Hook helpers must stay optional, stateless, redacted, and independently testable.
- Treat teaching-case results as evidence for teaching value, not as a release blocker unless they expose a plugin workflow failure.
# 当前执行面状态

跨系统编码与 argv 边界改进已落源码和离线验证入口。真实 provider、真实
Hook、Desktop、delegation、matched effect、formal cache 和 release gate 仍未
通过；本轮不把 model-free 或 fake-host 结果升级为真实宿主结论。

## 2026-07-23 最新真实 wire 结论

本轮没有读取或改写旧 gated-02，也没有重试任何已冻结请求。三个新身份各自只做一次 provider 请求：`loop-wire-02` 的 baseline 为 HTTP 400/4xx；`loop-wire-03` 只增加 Responses Lite header 后仍为 HTTP 400/4xx；`loop-wire-04` 保留 header、只把 input 改成 Codex `message[]` 后为 HTTP 502/5xx。

三次请求均连接建立、收到响应头、没有 terminal event、usage 为 0、请求计数为 1、自动重试为 false，失败层均冻结为 `protocol`。502 表明执行层发生变化，但不是成功证据；当前仍没有 `2xx + terminal + non-zero usage`，因此不创建新的 CLI canary，不启动真实 Hook、Desktop、delegation、matched、formal cache 或 release gate。离线 `codex-lite-minimal` profile 已准备但未连接真实 provider；源码与离线回归本轮实际为 `287/287` 通过。
