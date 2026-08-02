# Trusted Execution Surface

## Cross-system reliability

Executable wrappers are ASCII-only and pass paths and prompts through argv to
formal Python CLIs. Use `teaching/run_cross_system_validation.ps1` or the Bash
equivalent before any trusted-host task. Encoding, line ending, shell syntax,
and argv failures block the task; they are never classified as provider
failures. Real provider, Hook, Desktop, delegation, matched-effect, and release
gates remain independently fail-closed.

真实 provider/Hooks 验收必须在用户或租户明确批准的执行面运行。执行面是“Codex CLI 进程实际运行的位置及其网络外发策略”，不是 provider 地址本身。

`teaching/run_trusted_hook_host_local.ps1` 是 Windows 用户终端入口。它只创建全新 `communication-beta2-20260723-trusted-hook-01`，自动发现或读取 `CODEX_BIN`，校验 pinned `0.144.5` SHA，安装候选插件，使用非敏感 route/catalog 生成根级 TOML，并调用脱敏 Hook receipt runner。

硬边界：

- 不读取或修改旧 pilot、正式 cache、credential 或全局配置；
- route 写入所有 marketplace/plugin 表之前，避免 TOML 表作用域错误；
- request/stream retries 固定为 0；
- 原始 stdout/stderr、prompt、token、URL 和认证值不写入 receipt；
- 目录已存在、SHA 不匹配、route 不完整或 provider 执行面未获信任时立即停止；
- 入口不会绕过租户网络策略，也不会把 model-free 或 fake-host 结果升级为真实 Hook 通过。

用户应在已批准的可信终端中运行：

```powershell
powershell -File .\teaching\run_trusted_hook_host_local.ps1
```

也可先设置 `CODEX_BIN` 和 `CODEX_SOURCE_HOME`，避免脚本自动发现错误版本。输出只应使用新 host receipt 作为后续 Hook 门证据。
