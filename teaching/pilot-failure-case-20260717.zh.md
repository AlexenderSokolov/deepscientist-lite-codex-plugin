# 真实 Pilot 失败案例：首调用进程失败后的停止与留证

## 案例身份

- Pilot：`matched-pilot-20260717-01`
- 冻结源码：commit `83e2e3f5493896e9406813fd82c4600428d05ed6`
- 插件 tree digest：`9c59f899551e4d6c91d3ef3aabc057c5e2c18c85a854b131940d92ef2dde5648`
- 插件 manifest：`0.4.0-beta.2`；冻结快照包含八个技能
- Codex CLI：`0.144.5`
- 模型与推理预算：`gpt-5.6-sol / low`
- 单调用上限：900 秒
- 计划规模：18 次调用，覆盖 12 个 case-arm

工作区位于操作者指定的 `<WINDOWS_PILOT_ROOT>` 和 `<WSL_PILOT_ROOT>`。仓库文档不保存工作站绝对根目录。

## 可观察事实

第一项 `engineering-continuity--plain--r1` 启动后，receipt 先写为 `running / operator-stop`。约 767 秒后 Codex 进程以退出码 1 结束，最终 receipt 为：

| 字段 | 观测值 |
| --- | --- |
| status | `failed` |
| stop reason | `process-failed` |
| completed calls | `0/18` |
| input/output tokens | `0 / 0` |
| final message | 空 |
| session id | 已返回，但本文不保存其值 |
| workspace change | 未发现相对 baseline 的确认变更 |

session 事件中出现 `task_started` 和一个没有 `last_agent_message` 的 `task_complete`，没有结构化 authentication、model、rate-limit、connection 或 timeout 错误。上述证据不足以把根因归到任何一个外部服务或配置。

其余 17 次调用均未启动。WSL 数值 arm 未执行，因此没有 WSL computation proof，也没有 Linux Codex 安装证据。自动评分生成了 12 行 `incomplete`，所有效果比较指标保持 0；这不是 plain arm 的性能分数，而是“没有形成可评分结果”的状态记录。

## 为什么必须停止

执行器按 fail closed 规则在首个失败后停止。该请求已经获得 session id，但没有可确认 token、最终消息或任务产物，不能可靠判断外部服务端是否处理过请求。为避免 duplicate risk，禁止 resume、禁止自动重试，也不能删除失败记录后伪装成首次运行。

工程 round 1 原计划保留临时 session 供 round 2 恢复，并在 round 2 后逐 UUID 删除。由于 round 1 失败，隔离 home 中仍有临时 session 文件。它可能包含完整会话记录，不进入仓库、不作教学材料、不读取其正文；删除不属于原先“round 2 完成后删除”的授权范围，需由用户另行决定。

## 运行后修复

冻结 pilot 不回写。仓库中的后续 runtime 已增加脱敏进程诊断：只保存 stderr 类别、行数和 SHA-256，不保存 stderr 原文、隐藏推理、secret 或完整 JSONL。fake Codex 测试证明包含 secret 的 stderr 不会进入 receipt。

这项修复只能改善未来故障的可诊断性，不能解释本次失败，也不能把同一 pilot 变成可重试。

## 教学讨论

1. `task_complete` 事件不等于有可用最终结果；应同时核对进程退出码、token、最终消息和产物。
2. 没有产物不等于请求必然未到达外部服务。transport 结果不明时，重复提交本身是风险。
3. 真实 pilot 的价值不只在完整比较。一次正确停止能验证 receipt 预写、单请求串行、blocked 状态和 no-retry 约束。
4. 自动评分必须把缺失结果写成 `incomplete`，不能用 baseline 文件或流畅说明填补为模型成绩。
5. 本案例不支持任何 arm 优劣、统计显著性、reserved profile 或 `0.5.0-beta.1` 发布结论。

未来若重新执行，应使用新的 pilot id 与全新输出根，先单独解决 CLI 外部依赖，并再次取得授权；不得对 `matched-pilot-20260717-01` 调用 resume。
