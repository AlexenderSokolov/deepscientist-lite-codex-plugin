# DeepScientist Lite 真实 Wire/Host 验收记录（2026-07-21）

## 目标

在不读取、重放或改写 `communication-beta2-20260720-gated-02` 的前提下，先证明 provider Responses 真实链路，再决定是否进入 Codex CLI canary、Hook host、真实 delegation、matched effect、formal cache 和 fresh host 验收。

## 授权边界

- 复用当前进程环境中的 `OPENAI_API_KEY`，密钥只驻留内存。
- 每个真实假设最多一次请求；不自动重试。
- 不保存 raw stderr、raw response、endpoint URL、prompt、credential、完整环境变量或 workstation root。
- 不删除、reset、checkout、clean、commit、push、tag 或发布。
- 任一真实门失败时冻结当前身份并停止后续门。

## 已观察事实

- `communication-beta2-20260720-wire-diagnostic-01` 使用 fresh F/G 根目录运行；`prepare`、`preflight` 和 DNS/TCP/TLS 网络探针通过。
- 首次 authenticated minimal Responses SSE 请求收到 provider 侧 `4xx` 响应头、连接已建立、无 terminal event、usage=0、无输出、请求次数为 1、无自动重试；旧归约器把该形态误标为 `child-process`。
- 已修正 `teaching/transport_diagnostics.py`：收到 provider `4xx` 响应头但无 terminal/usage 时归为 `protocol`，而不是子进程失败。
- `communication-beta2-20260720-wire-diagnostic-02` 作为修复后的 fresh 身份运行；`prepare`、`preflight`、固定 Codex `0.144.5` SHA 校验、环境 key 类别、route fidelity、零重试、model catalog、DNS/TCP/TLS 均通过。
- `wire-diagnostic-02` 的 authenticated minimal Responses SSE 仍冻结：`http_status_category=4xx`、`connection_state=established`、`response_header_state=received`、`terminal_event_observed=false`、`usage=0`、`output_observed=false`、`request_count=1`、`automatic_retry_observed=false`、`failure_class=protocol`。

## 证据路径

- `F:\DeepScientistLitePilots\communication-beta2-20260720-wire-diagnostic-01\rounds\00-prepare.json`
- `F:\DeepScientistLitePilots\communication-beta2-20260720-wire-diagnostic-01\rounds\01-preflight.json`
- `F:\DeepScientistLitePilots\communication-beta2-20260720-wire-diagnostic-01\rounds\02-network.json`
- `F:\DeepScientistLitePilots\communication-beta2-20260720-wire-diagnostic-01\rounds\03-responses.json`
- `F:\DeepScientistLitePilots\communication-beta2-20260720-wire-diagnostic-02\rounds\00-prepare.json`
- `F:\DeepScientistLitePilots\communication-beta2-20260720-wire-diagnostic-02\rounds\01-preflight.json`
- `F:\DeepScientistLitePilots\communication-beta2-20260720-wire-diagnostic-02\rounds\02-network.json`
- `F:\DeepScientistLitePilots\communication-beta2-20260720-wire-diagnostic-02\rounds\03-responses.json`

这些路径是本机证据位置；公开报告不得复制其中的 endpoint、raw response 或任何 credential。

## 失败层

当前失败层收窄为 configured Responses route 的 provider/model/parameter acceptance。已排除本次尝试中的本地 DNS/TCP/TLS 不可达，也已排除隔离配置遗漏 `requires_openai_auth` 作为当前阻塞原因。

## 未验证项

- Codex CLI/provider wire compatibility
- Hook host loading
- 真实 child-agent dispatch
- matched effect
- formal cache
- fresh Desktop host
- 真实 Agent 表达改善
- release readiness

## 验证命令与结果

- `C:\ProgramData\anaconda3\python.exe -m unittest tests.test_transport_diagnostics -v`：7 项通过。
- `C:\ProgramData\anaconda3\python.exe -m unittest discover -s tests -v`：205 项通过。
- `C:\ProgramData\anaconda3\python.exe tools\validation\validate_repo.py`：通过。
- `git diff --check`：退出码 0；仅有既有 CRLF/LF 规范化警告。

## 唯一下一步

设计一个新的 fresh 诊断身份，专门验证 provider/model/parameter acceptance：例如只保留脱敏 HTTP 类别、error shape、allow-listed code/type、terminal event 和 usage，不保存 raw body；每个候选请求形状最多一次。该诊断通过前，不创建 `communication-beta2-20260720-gated-03`，不启动 CLI canary、Hook host、真实 delegation、matched effect、formal cache 或发布门。

## 后续事实（2026-07-21）

`communication-beta2-20260720-wire-diagnostic-03` 已通过 provider Responses 探针：HTTP 200、terminal event、非零 usage、单次请求。`communication-beta2-20260720-gated-03` 的 CLI canary 仍以认证 4xx 冻结；修复隔离 route 的非敏感 `env_key=OPENAI_API_KEY` 后，新的 `communication-beta2-20260720-gated-04` CLI canary 通过。随后在全新隔离 host-01 中，真实 `codex plugin marketplace` 与 `plugin add` 安装了候选版本、九个技能和 `hooks/hooks.json`；但全新 CLI 任务没有产生 JSONL 事件，故 host 门冻结。该失败不证明 Hook 未加载或 provider wire 不兼容，只证明本次 fresh CLI 进程没有形成可审计终态；不重试同一 host 身份。真实 Hook、Desktop fresh task、delegation、matched effect、formal cache 和 release gate 仍未验证。
