# 真实隐式 Canary 失败案例：2026-07-18

## 结论

第二次授权验收成功建立了九技能隔离 surface，并通过不调用模型的 preflight；随后唯一一次 180 秒隐式 canary 建立了 thread，但没有产生 turn terminal event、tool、usage 或最终反馈。外层监督在 244 秒停止等待时，canary receipt 仍为 `running`，相关 Windows `.cmd` 子进程树也仍存活；精确终止该树并关闭管道后，原 runner 在 378.098 秒处自行 finalize 为 `timeout`。

本轮按 fail-closed 规则冻结，不重试、不 resume、不进入 trigger campaign。脱敏诊断将 stderr 分类为 `rate-limit`，但没有保存原文，因此不能进一步解释具体 provider 响应。它不能证明隐式触发成功；只能证明 preflight surface 成立、真实请求未完成，以及原执行器的 Windows 超时收束存在缺陷。

## 预注册边界

- pilot id：`matched-pilot-20260718-01`
- 固定 CLI：`0.144.5`
- 模型配置：`gpt-5.6-sol/low`
- 授权引用：`user-approved-e1-20260718`
- control home：零技能
- DS Lite home：九技能
- canary：普通隐式提示、read-only、ephemeral、最长 180 秒、只允许一次
- 禁止：trigger campaign、18-call pilot、真实委派、cache 安装和发布

旧 pilot `matched-pilot-20260717-01` 没有被读取、resume、删除或回写。

## Preflight 证据

第一次 preflight 只因隔离 home 的 `login status` 未看到全局 `auth.json` 而 blocked。全局 CLI 实际由 `OPENAI_API_KEY` 环境类别供给认证；复制 credential 会破坏隔离与安全边界，所以实现改为只记录环境认证是否存在，不保存值。

修复后的 preflight 通过以下检查：

- CLI 版本为 `0.144.5`；
- 认证来源分类为 `environment-api-key`；
- `hooks`、`plugins`、`multi_agent` 为 stable/enabled，`plugin_hooks` 为 removed/disabled；
- control prompt surface 为零技能；
- DS Lite prompt surface 精确包含九技能；
- WSL 发行版与数值任务根可用；
- 冻结插件 tree digest 未漂移；
- 未保存认证原文、完整 prompt input、环境变量、secret 或工作站绝对根目录。

第一次 blocker 另存为 `results/preflight-blocked-auth.json`，没有被改写成通过。

## Canary 可观察事实

canary 启动前写入 `results/canary.json`，状态为 `running`。最终 terminal receipt 记录：

- thread/session 已建立；
- total tokens 为 0；
- `turn_completed=false` 且 `turn_failed=false`；
- tool count 为 0；
- 没有最终反馈；
- stderr 只保存 `rate-limit` 类别、14 行和 SHA-256；
- 工作区未修改；
- blocking reasons 为 execution timeout、缺反馈、零 usage、缺工具观察和缺隐式 skill 证据；
- receipt 最终状态为 `timeout`，耗时 378.098 秒。

这些事实支持 rate-limit 类别，但不足以复原精确 provider 错误或解释为什么没有 terminal turn。不得把进程树缺陷写成 provider failure 的原因。

## 已确认的执行器缺陷

Windows 上固定 CLI 通过 `.cmd` 包装器启动。旧超时逻辑只终止包装进程，Node/Codex 子进程成为孤儿并继续持有 stdout/stderr 管道，Python runner 因而无法 finalize receipt。

确定性回归测试使用 `.cmd → Python worker → child process` 复现该结构：0.05 秒预算在旧实现下约 2.19 秒后才返回。修复后 Windows 在父子关系仍存在时使用 `taskkill /T /F` 终止整棵树，同一测试约 0.7 秒返回并写出 terminal `timeout` receipt；非 Windows 仍使用 terminate 后必要时 kill 的路径。

这个修复只改善未来超时收束。当前 receipt 的 terminal timeout 是原 runner 在管道关闭后自行写入，不是手工回写；修复仍不能解释 provider failure。

## 操作处置

确认现场后，只终止了本次 canary 的 PowerShell、Python、Node 和 Codex 四个精确 PID，复核均已退出。没有停止其他 Codex 任务，没有重放请求，也没有读取会话缓存。

子进程管道关闭后，原 runner 把 `canary.json` 从 running finalize 为 terminal timeout。该终态、0 token/tool、空反馈和 rate-limit 分类共同冻结整个 pilot。

## 教学问题

1. 为什么“技能已注入 prompt”不能推出“隐式触发成功”？
2. 为什么认证类别存在仍不能代替一次真实完成事件？
3. 为什么 wrapper 退出、worker 退出、provider 请求结束和 receipt finalize 是四个不同事实？
4. 为什么必须区分“监督时观察到 running”与“原 runner 随后自行 finalize 为 timeout”？
5. 为什么本轮不能自动重试，即使新代码已经修复了进程树收束？

## 下一门

E2 trigger、Hook fresh-host、18-call pilot、委派、cache 和发布全部保持未授权、未验证。下一次真实 canary 必须使用新的 pilot id、新输出根和新授权；不能复用本轮 receipt。
