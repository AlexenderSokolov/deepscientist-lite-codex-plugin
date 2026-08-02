# DS Lite 0.8.1 验收与发布交接分析（2026-07-30）

## 目的与边界

本文是下一轮验收对话的唯一工作说明，不是发布证明。目标是完成 DS
Lite 0.8.1 的真实宿主验收、严格聚合与发布后复核。当前不得发布、不得
把本地单测或相邻 receipt 推断为真实宿主通过。

本次交接已核对：

- handoff：`research/artifacts/handoff-20260728-continuation.json`
- schema：`ds-lite.handoff.v1`
- `context_digest`：
  `9695819bc5a0b056b34cccc77fa9a3806a66c9cc8f3436c2e2f0647de1d8aa71`

所有新运行身份必须创建在 `research/.validation-tmp/<new-identity>/`。
禁止使用系统盘临时目录；禁止删除目录、覆盖 receipt、重跑任何冻结身份。
工作树已有大量用户和验收变更，发布时只能选择已经验证且属于 DS Lite 的
变更，绝不可 reset、clean 或回退无关内容。

## 控制面结论

Hook、runner 和 DAG 的职责必须严格分开：

| 层 | 已实现的职责 | 不能声称的职责 |
|---|---|---|
| Hook | 在 `UserPromptSubmit`、`PostToolUse`、`Stop` 判定是否允许收束；输出 `allow`、`block-and-resume` 或 `block-awaiting-user-action` | Hook 本身不能创建新的 Codex turn |
| persistent runner | 保存 session id、锁和 owner token；对同一 session 调用 `codex exec resume`；在 completion report 不合规时续跑 | `Stop:block` 不等于已执行 resume |
| autonomy DAG | 并行推进没有依赖关系的 ready gate；为失败生成结构化 receipt | 一个 gate 的 blocked 不能伪造为整体完成 |

精确的 Stop-first 通过条件只能是：

```text
Stop:block
  -> 外部 runner/app-server 在同一线程提交 continuation
  -> completed controller summary
  -> Stop:allow
```

若观察到 `Stop:block + turn/completed`，但未观察到 continuation，receipt
必须是 `blocked/hook-continuation-not-observed`。`turn.completed`、Hook 配置
可见、controller summary 文件存在，均不能替代第二个 turn。

## 当前 gate 状态

下表以最新独立 receipt 为准。旧 aggregate
`research/artifacts/formal-release-gate-20260729-04.json` 已过时：它尚未吸收
新的 CLI 与 provider receipt，但仍正确地拒绝发布，因为其他 required gate
没有通过。

| Gate | 当前状态 | 主要证据 | 说明 |
|---|---|---|---|
| source | passed | aggregate 中 `source-acceptance-20260728-continuation-01.json` | 保持冻结 |
| offline | passed | `offline-acceptance.json` | 保持冻结 |
| cli | passed | `research/.validation-tmp/cli-rust-20260729-06/receipt.json` | 观察到 `thread.started`、`turn.started`、`turn.completed` |
| provider | passed | `research/.validation-tmp/provider-acceptance-20260729-06/receipt.json` | 四个公开学术 provider 全部匹配；这只证明该 provider gate，不证明 Codex app-server 模型运行时 |
| delegation | passed | `delegation-acceptance.json` | 保持冻结 |
| formal_cache | passed | `formal-cache-acceptance.json` | 不等于 Desktop discovery |
| docs | passed | `docs-acceptance-20260729-01.json` | 保持冻结 |
| session_control | passed | `app-server-conversation-control-20260728-17.json` | UserPrompt-first 证据，不替代 Stop-first |
| web | passed | `web-benchmark-acceptance-20260729-03.json` | 保持冻结 |
| wsl | passed | `wsl-tmux-acceptance-20260728-resume-01.json` | 保持冻结 |
| matched_effect | blocked | `matched-effect-20260729-08-windows`、`-09-windows` | 两个 pilot 均冻结 |
| app_server_continuation | blocked | `research/.validation-tmp/appserver-continuation-20260729-11/app-server-continuation.json` | Hook 已信任，但在 Stop 前 error/terminal |
| hook | not-verified | 旧 trusted-hook 生命周期没有独立终态通过 receipt | 本地测试和 Hook 列表不可替代 |
| fresh_desktop | not-verified | 无独立 fresh Desktop receipt | CLI/cache/app-server 不可替代 |
| openscience | not-verified | fresh task 曾被 app-server terminal 阻断 | 需新身份 |
| strict complete profile | blocked | `formal-release-gate-20260729-04.json` | 必须等待全部 required gate 通过才可重建 |
| post-release | not-started | 无 | 必须在 strict profile 通过之后 |

## 阻断门的根因与恢复动作

### 1. matched_effect

冻结身份 `matched-effect-20260729-08-windows` 在六个 control 调用后，DS
Lite 调用收到 `rate-limit`。身份 `matched-effect-20260729-09-windows` 的
preflight 与 canary 已通过，但首个完整 workload control 调用收到
`transport`。两个结果都属于外部瞬态失败的证据，不能 resume 或覆盖。

下一轮应创建全新 identity，例如 `matched-effect-20260730-10-windows`，并
**必须**按以下完整序列运行：

```text
prepare -> install -> preflight -> canary -> run
```

`install` 不能省略；否则不会生成隔离 home 的 `home-manifest.json`，结果不具
备验收资格。新运行仍发生 408/429/5xx、DNS、reset 或 timeout 时，写新的
redacted terminal receipt，按服务端 `Retry-After` 或指数退避创建下一身份。
发生 401/402/403、配额/支付、协议非法、session drift 或 owner conflict 时，
应冻结该新身份并把 gate 标为 `awaiting_user_action` 或不可恢复，不能热循环。

只有 `4 cases x 3 arms` 的完整执行、盲审隔离和终态 matched-effect receipt
均 `passed` 时，此门才能关闭。

### 2. app_server_continuation

最新身份 `appserver-continuation-20260729-11` 有四个受信任 plugin Hook；它
只观察到 `user-prompt-submit:allow`，随后 error 和 `turn/completed`，没有
Stop 事件。因此它的真实结论是 `blocked/app-server-terminal`，而不是
`hook-continuation-not-observed`。

恢复顺序：

1. 先做一次受限、脱敏的 app-server 诊断。诊断只输出错误类别和摘要 hash，
   不保存 prompt、原始错误、环境或凭据。
2. 只有分类为 transport、timeout、408、429、500、502、503 或 504 时，才
   创建新的 Stop-first identity；协议、认证、配额、Hook trust、session
   identity 问题必须冻结，不能重复打同一接口。
3. 新 identity 使用 pinned Codex `0.144.5`、隔离 `CODEX_HOME`、隔离
   workspace、受信任 Hook 和 `--direct-egress` 的已授权最小路由。
4. 首 turn 必须真正触发 `Stop:block`。随后 external runner 在**同一
   app-server thread** 发起第二个 `turn/start`，controller summary 完成，
   第二个 Stop 为 `allow`。
5. 如果首 turn 已有 `Stop:block` 但第二个 turn 不存在，即使 summary 文件已
   写入，也必须写 `blocked/hook-continuation-not-observed`。

不能再将 UserPrompt-first 的 `session_control` receipt 误当作 Stop-first
通过。它们是两个故意独立的协议。

### 3. real Hook lifecycle

现有 source-level Hook 测试、`hooks/list`、formal trust write 和
UserPrompt-first 通过结果只证明部分控制面。此 gate 需要自己的 fresh host
receipt，覆盖真实 Hook 触发、controller ownership、终态 summary 和收束。

应在 app-server 能稳定到达 Stop 阶段后，创建全新 trusted-hook host identity
并执行 `run_trusted_hook_host_local.ps1` 的等价隔离流程。若模型 turn 在
Stop 前结束，写 `blocked/app-server-terminal`，不能把“Hook 已列出”升级为
`passed`。

### 4. fresh Desktop

当前没有真实 Desktop discovery 证据。正式 cache、CLI 的 `plugin list`、
app-server 静态 Hook 数据都不代表 Desktop 已发现插件或宿主能够执行它。

应在 Codex Desktop 中创建一个**新的** task 和隔离 project/workspace，完成：

1. 从 fresh marketplace/cache 发现 DS Lite 0.8.1；
2. 在该 Desktop task 中运行一个最小、无敏感数据的真实任务；
3. 观察 Hook/session-control 行为并写 redacted receipt；
4. 将 task identity、发现结果、终态和失败层写入独立 receipt。

旧 task `019faccb-04cc-72a3-866e-1d1fe1cc94f5` 不能作为新鲜身份复用。
computer-use 和 in-app browser 可作为宿主执行面协助操作，但它们的存在本身
不是 DS Lite 功能通过证据。

### 5. OpenScience

之前 fresh OpenScience task 在 app-server terminal 前结束。它不能与
provider、Web 或 docs receipt 合并推断通过。待 app-server 真实 turn 恢复后，
创建新身份运行其非敏感最小任务；若仍在 Hook/Stop 前 terminal，保留该
`blocked/app-server-terminal` receipt，同时继续其他无依赖门。

## 自动恢复策略

共享分类器 `ds_lite_recovery.py` 的唯一用途是给 runner、autonomy 和
app-server harness 一致的边界：

| 类别 | 处理 |
|---|---|
| DNS、连接重置、TLS/transport、408、429、500、502、503、504、timeout | 按退避和抖动自动安排新身份；保留旧身份 receipt |
| 401、402、403、配额、支付、授权/路由 | `awaiting_user_action`；不消耗式重试；DAG 继续其他 ready gate |
| 400、422、畸形协议、session drift、缺失 session id、重复 owner、Hook trust | 不可自动恢复，冻结身份 |
| 未知外部错误 | 一次受限诊断加一次安全尝试；仍未知则 `awaiting_user_action` |

每一份新 receipt 至少应记录：`status`、`failure_layer`、`recovery_class`、
`attempts`、`automatic_retry_observed`、`next_automatic_action`、可逆摘要
hash，以及不含敏感内容的证据引用。

## 推荐执行 DAG

```text
provider 已通过
    |
    +--> new matched-effect pilot ------------------+
    |                                                |
    +--> bounded app-server diagnosis -> Stop-first -+--> strict complete profile
                                         |            |
                                         +--> Hook ----+
                                         +--> OpenScience

fresh Desktop ---------------------------------------+

strict complete profile passed
    -> full repository verification
    -> ownership audit
    -> selective commit/tag/push
    -> remote tag/marketplace/cache verification
    -> post-release receipt passed
```

`fresh Desktop` 不依赖 matched-effect；若 Desktop 宿主可用，它应与
matched-effect 和 app-server 诊断并行推进。app-server 停止或等待用户动作时，
不得停止无依赖 gate。

## 严格聚合与发布判定

保留 `formal-release-gate.v2` 的兼容行为，但使用 profile
`ds-lite-0.8.1-complete`。聚合器应要求下列 gate 各有一个 schema 匹配的、
独立的 `passed` receipt：

```text
source, offline, cli, provider, hook, delegation, matched_effect,
formal_cache, fresh_desktop, docs, openscience,
app_server_continuation, session_control, web, wsl
```

聚合器必须拒绝缺失、重复、schema 不匹配、非 `passed` 和相邻证据推断。严格
aggregate 通过前，不应创建 post-release receipt，更不能 commit、tag、push
或报告发布完成。

所有 gate 通过后，发布顺序固定为：完整 unittest、`validate_repo.py`、六包
和安装矩阵、PowerShell/Bash 检查、`py_compile`、`git diff --check`、工作树
归属审计、选择性提交、tag、push、远端 tag/marketplace/cache 验证、写
post-release receipt。任一步失败，最终状态仍是 blocked/failed。

## 下一轮启动清单

1. 先重新校验本文件列出的 handoff digest，并读取 `PROJECT.md`、最新
   receipt、Git status。
2. 读取最新 `research/.validation-tmp` 目录，确认没有其他 worker 已创建同名
   identity 或新的 receipt。
3. 创建新的 matched-effect identity，完整执行五阶段；不要触碰 `-08`、`-09`。
4. 对 app-server 做一次受限分类诊断，并严格按照上述分类决定是否创建新
   Stop-first identity。
5. 并行安排真实 fresh Desktop。其失败不能阻断 matched-effect。
6. 每 60 秒持久化并报告：已通过门、运行门、冻结门、证据路径、当前 identity
   与下一自动动作。
7. 仅在所有 required receipt 和 post-release receipt 都通过后发布。

