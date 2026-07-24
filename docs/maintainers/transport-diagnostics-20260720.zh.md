# Transport 诊断与离线协议验收（2026-07-20）

## 目标

在不读取、重试或改写 `communication-beta2-20260720-gated-02` 的前提下，提高未来 pilot 的 transport 可诊断性，并让 Hook、delegation 和 matched comparison 的文件协议在真实 provider blocked 时仍可做确定性验收。

## 事实与假设

- gated-02 已证明 route/catalog copied、preflight passed；唯一真实 canary 建立 thread 后以 `transport` 失败，0 usage、0 tool、无 terminal/final feedback。
- 旧 receipt 没有足够结构化信息继续细分 transport 根因，不能追溯改写。
- provider 或 CLI 未公开的连接、response header 和 error code 必须保留为 `unknown` / `not-observed`，不得从 thread id 猜测。

## 授权边界

- 本轮只运行本地 loopback fake provider、fake Codex 子进程和源码协议 helper。
- 未读取 F/G 下旧 pilot，未调用真实 provider，未修改正式 cache、credential、marketplace 或全局配置。
- 未启动真实 Hook host、子智能体、matched comparison、fresh host 或发布流程。

## 实现

- `teaching/transport_diagnostics.py` 提供 `ds-lite.transport-diagnostic.v1`，保存 normalized failure class、HTTP 类别、allow-listed provider code、连接/header 观察、subprocess/child/pipe 状态以及 stderr 行数和 SHA-256；不保存 stderr 原文。
- `teaching/pilot_runtime.py` 在 success、failure、timeout、ambiguous 和 spawn error 上都附着终态诊断；spawn error 不再把 receipt 留在 `running`。
- 隔离 provider route 固定 `request_max_retries=0`，不继承正式 home 的重试值。
- `teaching/offline_acceptance.py` 生成 fresh-only `ds-lite.offline-protocol-acceptance.v1`；已有输出路径拒绝覆盖，且 `real_gates_unlocked` 永远为 `false`。

## 实际命令与观察

```powershell
$env:TEMP=(Resolve-Path '.validation-tmp')
$env:TMP=$env:TEMP
& $env:PYTHON_BIN -m unittest tests.test_transport_diagnostics tests.test_offline_acceptance tests.test_pilot_runtime tests.test_acceptance_gate tests.test_hooks tests.test_delegation_probe tests.test_teaching_labs tests.test_explainability_score -v
```

观察：89 项测试通过，0 failure、0 error。

```powershell
powershell -ExecutionPolicy Bypass -File teaching\run_transport_diagnostics.ps1 -Output .validation-tmp\offline-acceptance-20260720-02
```

观察：`overall_status=passed`。success、auth、rate-limit、network、malformed response、child early exit、ambiguous 共七个场景各启动一次 fake Codex；除 child early exit 为 0 次 provider 请求外，其余均为 1 次。所有场景 `automatic_retry_observed=false`、`raw_stderr_persisted=false`。

```powershell
powershell -ExecutionPolicy Bypass -File tools\validation\run_validate.ps1
bash tools/validation/run_validate.sh
```

观察：PowerShell 与 Bash 入口分别运行 189 项测试并通过；Bash 入口有 1 项按平台条件跳过。两个入口随后执行仓库 validator 和清单内 `py_compile`，整体退出码均为 0。

## 证据与结论层级

- 证据：`.validation-tmp/offline-acceptance-20260720-02/offline-acceptance.json`
- Hook：`fake-host-tested / real-host-not-verified`
- Delegation：`protocol-tested / host-dispatch-not-verified`
- Matched comparison：`prepared-and-freeze-tested / effect-not-measured`
- Transport：fake reducer 与一次请求边界通过；真实 provider 和真实 Codex wire compatibility 未验证。

## 失败层与未验证项

当前真实失败层仍为 gated-02 receipt 所支持的 `transport`，具体根因未知。正式 cache、fresh host、Hook loading、真实 delegation、真实 matched comparison、真实 Agent 表达和发布 readiness 均未验证。

## 唯一下一步

完成仓库完整验证后停止。若所有离线门继续通过，再单独申请 `communication-beta2-20260720-gated-03` 的新 F/G 根目录与一次真实 canary 授权；在授权前不得创建或运行该 pilot。
