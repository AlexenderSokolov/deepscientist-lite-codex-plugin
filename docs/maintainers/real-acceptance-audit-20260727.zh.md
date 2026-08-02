# DeepScientist Lite 0.8 续验审计表（2026-07-27）

本表只记录本轮新观察。`passed` 仅适用于对应行，不能推断相邻宿主门；旧 pilot、cache 和 receipt 不被重跑或覆盖。

| 门 | 本轮证据 | 状态 | 下一动作 |
|---|---|---|---|
| 完整离线回归 | `417/417` unittest；Nature 回归 `8/8` | `passed` | 不解锁真实宿主门 |
| 本轮新增回归 | Web/OpenCLI/Codex pin 相关测试 `31/31`；仓库 validator 与六包矩阵通过 | `passed` | 不推断真实 provider 或 Desktop |
| 六包与八矩阵 | `G:\DS-Lite-validation\package-validation-20260727-rerun.json` | `passed` | 仍需 fresh marketplace cache |
| Codex pin | `G:\DS-Lite-validation\codex-pin-20260727-02\codex-pin.json`；0.144.5 与冻结 SHA 匹配 | `passed` | 仅用于新的真实宿主身份 |
| Hook 协议 | `trusted-hook-20260727-04` 真实观察危险 `PreToolUse block` 与首次 `Stop block`；`trusted-hook-20260727-06` 在预闭合 fixture 上真实观察合法 `PostToolUse allow` 与 `Stop allow`；聚合 receipt 保留 closure 限制 | `passed`（两宿主事件门） | agent 自主完成终态闭合仍为 `not-observed`，不影响本事件门但不得夸大 |
| Web public-only | 标准库 `example.com` 抓取通过；OpenCLI OpenAlex 通过；OpenCLI arXiv 30 秒超时 | `partial` | 完成 10 案例 benchmark；Playwright 仍未发现 |
| OpenCLI challenger | `@jackwener/opencli` 1.8.6；public manifest 检查通过；OpenAlex source-record.v2 已生成 | `partial` | 保持非默认后端，继续记录 arXiv/network 失败 |
| Academic provider | fake provider/fixture | `not-verified` | 授权 Crossref/OpenAlex/Semantic Scholar/arXiv live pilot |
| 长任务/tmux | bootstrap 计划已生成 | `awaiting-user-bootstrap` | 用户在独立 WSL shell 执行并回传 fingerprint |
| Delegation | Codex Desktop `desktop-delegation-20260727-02` 真实派发两个互斥 child，父级唯一整合；独立 partial child 保留 `blocked` 且未替换 | `passed` | 不推断 matched effect、formal cache、fresh Desktop 或发布 |
| Matched effect | 4-case x 3-arm 已冻结，未真实调用 | `not-verified` | 完成 12 arms 预注册调用和盲评 |
| Formal cache | 源码包验证通过，fresh cache 未观察 | `not-verified` | 标准 marketplace 安装六包矩阵并重启 Desktop |
| Fresh Desktop | 无 fresh task ID | `not-observed` | 用户创建 fresh Codex/OpenScience task 并回传 ID |
| OpenScience | fresh task `wx-acp-codex-o9cq80xQ` 使用 Core+Web+Knowledge；仅访问 `api.openalex.org`；`source-record.v2`、Evidence Pack 与 `verify --strict` 均通过，Science panel 已发布 E1/E2 | `passed` | 不推断 provider、Hook、delegation、formal cache 或 fresh Desktop |
| Release | `G:\DS-Lite-validation\formal-gate-20260727\gate-rerun4-openscience-passed.json` | `blocked` | 所有独立 receipt passed 后才提交、合并、打 tag、发布 |

## 本轮代码修复

1. Hook JSON stdout 改为 ASCII-safe，并显式按 UTF-8 解码 stdin，修复 Windows 中文路径路由。
2. Learning receipt 对磁盘中规范化后的摘要（含结尾换行）计算哈希，修复复用时的假 stale。
3. Nature snapshot 校验排除解释器生成的 `__pycache__`、`.pyc`、`.pyo`，避免把运行时缓存当作上游漂移。

## 用户动作请求

## Hook 真实事件闭环

- Host A：`G:\DS-Lite-validation\trusted-hook-20260727-04\hook-host.json`，真实 provider turn，观察到 `UserPromptSubmit allow`、危险 `PreToolUse block`、合法 `PostToolUse allow` 与首次 `Stop block`；Graph revision 保持为 0。
- Host B：`G:\DS-Lite-validation\trusted-hook-20260727-06\hook-host.json`，固定 Codex `0.144.5` 与 SHA 通过，短只读 provider turn 观察到 `UserPromptSubmit allow`、`PreToolUse allow`、`PostToolUse allow`、`Stop allow`，无自动重试。
- 聚合：`G:\DS-Lite-validation\trusted-hook-20260727-06\trusted-hook-acceptance.json`。Host B 的 iteration 由 fixture 在请求前合法闭合，receipt 固定记录 `agent_initiated_terminal_closure=not-observed`；因此通过的是四类 Hook 事件门，不是“agent 已自主完成闭环”的效果声明。

Codex pin 已由 Agent 自动取得并验证。WSL 长任务、真实 delegation、matched effect、fresh Desktop 和发布仍分别保持未验证，不得由本轮 Web、pin、Hook 或 OpenScience 证据推断。

## 真实 delegation canary（冻结）

`G:\DS-Lite-validation\real-delegation-20260727-01\delegation-canary.json` 记录了固定 Codex CLI 的一次真实、只读 provider turn。CLI task 终态通过、无自动重试，但 collaboration 汇总只有 `wait=2`，`spawn_agent=0`、receiver=0；该失败身份仍被冻结，不被覆盖。

随后在实际 Codex Desktop 受信任执行面完成新身份 `research/desktop-delegation-20260727-02/`：两个 child 分别仅写入 `child-a-result.md` 与 `child-b-result.md`，父级独自写入 integration。`host_acceptance.audit_delegation` 复验 `spawn_agent=2`、receiver=2、独立 result ref、`nested_delegation=false` 与 parent-only integration。另一个真实 child 因 formal-cache receipt 未作为输入被保留为 `blocked`，没有替换 child 或自动重试。总 receipt 为 `research/desktop-delegation-20260727-02/delegation-acceptance.json`；该门现为 `passed`，但不替代其余独立发布门。

## 前台 auto-resume 真实验收

新身份 `G:\DS-Lite-validation\autoresearch-resume-20260727-04` 使用固定 Codex
`0.144.5`、固定 SHA-256 和隔离构建的 `codex-autoresearch 0.1.5-beta.0` 适配身份。
它在同一 session 中真实完成两轮：第一轮严格载体为 `partial(g1)`，仅产生
`evidence/g1.txt`；第二轮由 `codex exec resume` 完成 `completed(g1,g2)` 并产生
`evidence/g2.txt`。`ds_lite_loop.py verify` 返回 `passed`，两轮 session hash 相同，
未保存原始 JSONL 或 prompt。此前 `...-03` 曾因旁路工具文本包含授权词被错误归类为
`auth`，该身份已冻结保留；修复后新增回归覆盖“严格终态优先于旁路诊断”。

这证明前台、有界的 partial -> same-session resume -> strict completion 闭环已真实观察到；
它不证明 matched effect、正式 cache、fresh Desktop 或发布门。

## Academic live-provider 自动重试

### 2026-07-28 连续推进补充证据

- 控制器连续性：`tests/test_autonomy_controller.py` 的 7 项均通过，覆盖前序 gate 冻结后继续独立 gate、幂等瞬态失败最多六次、静默 receipt 轮询，以及 `--resume` 只运行剩余 gate。每个终态进度回执现在固定写明执行原因、实际动作、证据、失败层和下一自动动作。
- 源码与包回归：在新的 G 盘临时根完成 `435/435` unittest、`tools/validation/validate_repo.py` 和全六包矩阵。这只属于源码和包协议证据，不构成宿主或发布通过。
- Web public-only：`G:\\DS-Lite-validation\\web-live-20260728-01` 成功将 `example.com` 与 arXiv RSS 写为带哈希的 `ds-lite.source-record.v2` 产物；同一身份的 2 MiB PDF 预算拒绝保留为失败记录。`...\\web-live-20260728-02` 成功抓取 W3C 小型公开 PDF；`...\\web-live-20260728-04` 用公开 URL 与不匹配 allowlist 验证联网前的 policy block，并写入完整失败 record。JS、中文文章、重复/变化内容、拒绝访问与非法 URL 尚未完成，因此 Web 仍为 `partial`。
- Academic live providers：`G:\\DS-Lite-validation\\academic-live-20260728-01\\academic-provider-acceptance.json` 对 Crossref、OpenAlex、Semantic Scholar 和 arXiv 发起经授权的公开元数据调用。Semantic Scholar 按许可的瞬态重试路径收束，arXiv 给出精确标识符匹配。receipt 为 `verified`、允许投稿，并为四个 provider 都留下终态结果。因此 Academic live-provider gate 为 `passed`，并以新的独立身份覆盖下文 2026-07-27 的历史 availability 判断；它不替代 matched effect、formal cache、fresh Desktop 或 release 证据。

`G:\DS-Lite-validation\academic-live-20260727-02\academic-provider-acceptance.json`
记录一次经授权的四 provider 公开元数据调用。Semantic Scholar 因持续 `429` 被自动执行
三次指数退避请求，arXiv 精确匹配成功；Crossref 与 OpenAlex 为 `not-found`。因此引用
检查本身为 `verified`，但“四 provider 全部可用”的验收门仍为 `blocked`，不能提升为
Academic provider gate 通过。实现现在只对 `timeout`、`rate-limit`、`network` 三类幂等
读取重试最多三次，其他失败不重试。

## 2026-07-28 会话自治收束验收

- 新身份 `G:\DS-Lite-validation\trusted-hook-20260728-01-conversation-autonomy` 在固定 Codex `0.144.5` 下真实加载 Hook，观察到 `UserPromptSubmit allow`、合法 `PostToolUse allow` 与危险 `PreToolUse block`。该 provider turn 在 125 秒超时且没有 terminal event，身份冻结为 `timeout`；它不构成 Stop 或对话续跑通过。
- 另一个全新身份 `G:\DS-Lite-validation\trusted-hook-20260728-02-stop-autonomy` 使用只含“立即结束”的最小 prompt。真实 host receipt 为 `passed`，存在 `turn.completed`，并真实观察到 `UserPromptSubmit allow` 与 `Stop block`。这证明活动 `ds-lite.autonomy-contract.v1` 可以在宿主会话收束时阻断提前结束。
- 本轮源码将活动合同的唯一后续动作固定为 `resume-autonomy-controller`，并在 `UserPromptSubmit`、`PostToolUse` 和 `Stop` 投影 `run_autonomy --resume`。Hook 不能自行创建后台执行面，因此本证据证明“收束被阻断并给出唯一续跑入口”，不证明模型已经自动执行该入口；后者仍需一个 `Stop block -> controller resume -> terminal summary -> Stop allow` 的独立新身份验收。

### 续跑语义复验

`trusted-hook-20260728-03-stop-continuation-prompt` 与
`trusted-hook-20260728-04-stop-continuation-boolean` 分别补发了专用 `prompt`，以及
`continue=true` 加 `prompt`。两者都真实记录 `Stop block`，但仍同时出现
`turn.completed`，没有第二次 hook 或 controller resume。因此在当前 pinned `codex exec`
执行面，Stop Hook 的调用和决策记录不等于会话续跑已经生效。`fresh_host_probe.py`
现将该组合强制归类为 `blocked / hook-continuation-not-observed`，避免将其误记为通过。
该限制不影响已观察的危险 `PreToolUse` 阻断；会话级自治仍需在支持 Stop continuation
的 fresh Desktop 交互执行面完成独立验收。

### App-server fresh-task continuation（2026-07-28）

- 交接入口 `research/artifacts/handoff-20260728-continuation.json` 已用 `ds-lite.handoff.v1` 校验通过；`context_digest=9695819bc5a0b056b34cccc77fa9a3806a66c9cc8f3436c2e2f0647de1d8aa71` 匹配。
- 旧身份 `research/artifacts/app-server-continuation-20260728-01.json` 保持冻结：`blocked / provider-destination-authorization`，没有 app-server 启动、thread 或 Hook 事件证据。
- 新身份 `research/artifacts/app-server-continuation-20260728-02.json` 启动了 app-server fresh thread，观察到 Desktop `userAgent` 和 `turn/completed`，但 `hook_event_counts={}`，没有 autonomy summary，因此不能进入 Stop continuation 判定。
- 修正后的验收 harness 在 `research/artifacts/app-server-continuation-20260728-03.json` 中额外记录 `hooks_list_observed=true`、`error_notification_count=1`、`terminal=turn/completed`、`hook_event_counts={}`、`autonomy_summary_completed=false`。该身份终态为 `blocked / app-server-hook-not-observed`。
- 本轮没有观察到 `Stop block`，因此不适用 `hook-continuation-not-observed`；若未来 fresh identity 同时出现 `Stop block` 与 `turn.completed` 但无 controller summary，仍必须写为 `blocked / hook-continuation-not-observed`，不得提升为通过。
- 当前结论：app-server surface 可见 installed plugin 和 hooks/list，但 fresh turn 未触发 DS Lite Hook event receipt；会话级自治门继续 blocked。下一步只应诊断 app-server hook loading / invocation surface，不得重跑冻结 identity、不得覆盖 receipt、不得发布。
### App-server fresh-task continuation follow-up (2026-07-28)

- Fresh identity `research/artifacts/app-server-continuation-20260728-04.json` used a new isolated app-server workspace and did not overwrite `...-01`, `...-02`, or `...-03`.
- The redacted `hooks/list` diagnostic observed four enabled plugin command hooks: `userPromptSubmit`, `preToolUse`, `postToolUse`, and `stop`. All four had `trustStatus=untrusted`; `error_count=0` and `warning_count=0`.
- The app-server turn still ended as `turn/completed` with one redacted `other` error notification, zero `hook/started` / `hook/completed` notifications, zero DS Lite Hook event receipts, and no autonomy summary.
- This identity is frozen as `blocked / app-server-hook-not-observed`. It still did not reach `Stop block`, so it must not be reclassified as `hook-continuation-not-observed`.
- Current next action: obtain or implement a trusted app-server Hook execution surface for a new fresh identity; do not release, publish, retry frozen identities, or infer Stop continuation from `hooks/list` alone.

### App-server 严格输出兼容复验（2026-07-28）

- `app-server-continuation-20260728-07` 在 provider/app-server 启动前因 fixture import 失败封存为 `blocked / fixture-import`；`...-08` 在 DS Lite 初始化前因 PowerShell 模板的 `Template` 转义缺陷封存为 `blocked / fixture-init`。两者均无 provider turn、Hook event 或 autonomy summary，未被重跑。
- 修复后，fresh `...-09` 通过正式 `config/batchWrite` 将四个 plugin command Hook 写入 `hooks.state` 并复核为 `trusted`。它实际写出 `UserPromptSubmit allow` receipt，但 app-server 将 Hook 标为 `failed`。pinned `0.144.5` 的公开 Hooks 源码确认原因：非空 JSON 必须匹配 event-specific schema，原内部 snake_case 诊断对象缺少 `hookSpecificOutput`。
- Core 现将内部结果投影为严格宿主 envelope：`UserPromptSubmit` 的上下文写入 `hookSpecificOutput.additionalContext`；Stop 阻断只写 `decision=block` 和非空 `reason`。该投影不保存原始 prompt、事件流或 app-server error 文本。
- fresh `...-10` 使用修复后的 Core，观察到 `hook/started:userPromptSubmit:running` 与 `hook/completed:userPromptSubmit:completed`，并写入 `user-prompt-submit:allow` receipt，证明 app-server Hook trust 与输出 schema 已实际生效。随后 turn 在 Stop 前以一个 redacted、非重试 `other` error 结束，未观察到 Stop block、controller resume、completed summary 或 Stop allow；receipt 终态为 `blocked / app-server-terminal`。
- 因没有 `Stop block`，`...-10` 不适用 `hook-continuation-not-observed`。该身份已经冻结；未知 `other` 类 error 不满足幂等瞬态重试条件。会话自治、formal cache、fresh Desktop、matched effect、Web 完整 benchmark 与 release 仍未完成，禁止汇总或发布。

### Stop 自动续跑与 app-server 续验（2026-07-28）

- Core 的 Stop Hook 现会在存在已批准且未终态的 `ds-lite.autonomy-contract.v1` 时，前台执行一次有 120 秒上限的 controller `--resume`。成功后当前 Stop 固定返回一次 `block`，要求宿主产生 summary turn；只有 controller summary 和 active iteration 均为终态时，下一次 Stop 才 `allow`。controller 失败则返回 `block`、不继续，也不产生后台任务或自动发布。
- 独立隔离证据 `research/hook-autonomy-auto-20260728-02/` 已观察到 `Stop block -> gate receipt passed -> completed summary -> Stop allow`。iteration `trusted-hook-running-01.json` 同时终态化，含 reflection 与 user report；此证据只证明本地 Hook/controller 闭环。
- Fresh `research/artifacts/app-server-continuation-20260728-14.json` 经正式 `config/batchWrite` 信任入口写入并复核四个 `trusted` Hook，且实际观察到 `UserPromptSubmit` Hook 完成。随后 provider response stream 在 Stop 前断连，receipt 冻结为 `blocked / app-server-terminal`。本次经授权仅内存查看错误文本，未写入 receipt、文件或日志；因此 app-server Stop 闭环和 release 仍为 blocked。

### Rust transport control evidence (2026-07-28)

- `research/artifacts/rust-provider-20260728-02.json` records the terminal
  result of the already-observed pinned control request after its absolute
  `CODEX_HOME` correction: `blocked / fresh-cli-host`, a normalized
  `stream-disconnect` class, and no persisted raw output, error text, or retry.
- Fresh `rust-provider-20260728-05` revalidated the pinned binary, isolated
  non-secret route, and direct egress, then ran exactly one minimal in-memory
  `reqwest/hyper/rustls` diagnostic. It exited nonzero before JSONL terminal,
  HTTP, TLS, HTTP/2, proxy, DNS, reset, or stream-disconnect observations. Its
  receipt is frozen as `blocked / fresh-cli-host` with no raw output retained.
- Neither Rust identity reached `Stop block`; neither may be classified as
  `hook-continuation-not-observed`. The app-server continuation and release
  gates remain independently blocked.

### Formal cache acceptance (2026-07-28)

- Fresh `research/formal-cache-20260728-01/formal-cache-acceptance.json` passed
  with the pinned `0.144.5` CLI. It created an isolated `CODEX_HOME`, registered
  the local marketplace, installed all six split packages, and observed the exact
  expected package/version set through `plugin list --json`.
- This identity made no model request and retained no raw command output or error
  text. It closes only the independent formal-cache gate; fresh Desktop,
  app-server Stop continuation, matched effect, Web completion, and release are
  still separate gates.
