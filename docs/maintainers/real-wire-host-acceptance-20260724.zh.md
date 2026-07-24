# 真实 Wire、CLI 与 Hook 门记录（2026-07-24）

## 本轮目标

在不读取、重放或改写旧 gated-02 的前提下，验证当前 pinned Codex 0.144.5
与 provider 的 Responses wire，并在 wire 通过后执行一次真实 CLI canary。
Hook host 只有在 CLI canary 通过且外发目的地获得信任后才允许启动。

## 实际观察

### `communication-beta2-20260724-wire-01`

- `prepare`、pinned CLI `0.144.5` SHA、route fidelity 和零重试 preflight 通过。
- DNS、TCP、TLS 单次探针通过。
- 唯一一次 authenticated `codex-lite-minimal` Responses SSE 请求通过：HTTP
  成功、terminal event=true、output=true、usage total=4412、request count=1、
  automatic retry=false。
- provider error object 未观察到；request-id 只保存 hash。
- 证据引用：`rounds/00-prepare.json`、`rounds/01-preflight.json`、
  `rounds/02-network.json`、`rounds/03-responses.json`。

### `communication-beta2-20260724-gated-cli-02`

- 使用正式 `pilot_runtime` 创建 fresh F/G 结构，候选版本 `0.6.0-beta.1`，
  26 个 skill，control/DS Lite 隔离 home 和 provider route 均通过 preflight。
- 单次 pinned CLI canary 通过：`turn_completed=true`、最终反馈存在、usage
  total=77706、tool_count=16、workspace unchanged=true、exit_code=0、acceptance
  gate=passed。没有自动重试。
- 证据引用：`results/preflight.json`、`results/canary.json`。

## Hook 门状态

计划中的 `trusted-hook-20260724-prompt` 在进程启动前被宿主安全策略阻断：
当前 provider 目的地未被证明为受信任，任务可能外发项目上下文。没有启动
Codex、没有发送 Hook 任务、没有创建可冒充成功的 receipt，也没有通过替代
通道绕过策略。因此四类 Hook host、后续 delegation、matched effect、formal
cache、fresh Desktop 和 release gate 全部保持 `blocked-by-policy / not-verified`。

## 授权边界与下一步

- key 只在当前进程内使用；receipt 不保存 key、URL、raw response、prompt、
  raw stderr、隐藏推理或绝对工作站根目录。
- 每个真实身份只请求一次；不自动重试，不修改旧 pilot、正式 cache、全局
  marketplace 或 credential。
- 唯一下一步：用户明确批准该 provider/tenant 作为受信任外发目的地后，重新
  创建新的 Hook fresh 身份；在此之前只继续 fake/offline 协议和文档工作。

## 结论

本轮已经证明真实 provider Responses wire 和 pinned Codex CLI canary 的完整
终态兼容；没有证明真实 Hook host loading、真实子智能体分发、matched effect、
formal cache、fresh Desktop 或 Agent 表达改善。发布状态仍为 beta candidate，
release gate 未通过。
