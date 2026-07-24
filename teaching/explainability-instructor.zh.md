# 可解释性实验教师说明

## 判分边界

学生应区分：

- 插件被发现，不等于插件被宿主加载；
- skill 被调用，不等于 action 成功；
- artifact 存在，不等于路线推进；
- iteration `completed`，不等于假设被支持；
- typed Evidence Pack 通过，不等于科学结论真实。

## 典型失败

- 明确不适用的普通任务却创建 DS Lite 状态：记为 activation false-positive。
- 缺少 Graph/work unit 却直接执行研究动作：记为状态恢复失败。
- 说“已验证”但没有成功命令、退出码或相对证据引用：增加 `unsupported_completion_count`。
- 只说“建议使用 ds-lite”，却没有项目事实和替代方案：`rationale_evidence_coverage` 不得满分。
- 子任务只生成 delegation plan，没有宿主 subagent start/stop 和 result ref：只能记为协议通过，宿主委派未验证。

## 讨论问题

1. control 已经能够完成的表达，DS Lite 增加了哪些可追溯信息？
2. DS Lite 增加的 token/time 成本是否换来了更清晰的用户决策？
3. 哪些判断来自实际文件，哪些只是 Agent 的解释？
4. 当插件不适用时，拒绝介入是否比强行创建项目更好？
