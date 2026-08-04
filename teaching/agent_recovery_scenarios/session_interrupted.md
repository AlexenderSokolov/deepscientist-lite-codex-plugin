# 会话中断恢复

> 场景：AGENTS 正在执行一个有界动作，会话突然中断。新会话需要接手。

## 症状

- 上一会话的聊天记录不可用或不完整
- `STATUS.md` 可能停留在"执行中"状态
- `research/state/graph.json` 的 `active_node_id` 可能指向未完成的节点

## 恢复步骤

1. **读取 `PROJECT.md`**：确认项目目标、假设和验收标准
2. **读取 `STATUS.md`**：查看上次记录的状态和下一步
3. **读取 `RESEARCH_MAP.md`**：查看研究路线和节点关系
4. **检查 Graph 一致性**：
   - 打开 `research/state/graph.json`
   - 确认 `active_node_id` 与 `STATUS.md` 中记录的活跃节点一致
   - 如果不一致，以 Graph 为权威
5. **检查 artifact 完整性**：
   - 查看 `research/artifacts/` 目录
   - 检查最近的 artifact 是否完整（有 `schema_version`、`status` 等必填字段）
   - 如果 artifact 不完整，标记为 `ambiguous` 或 `blocked`
6. **重建 STATUS**：根据 Graph 和 artifact 的实际状态，更新 `STATUS.md`
7. **继续执行**：从 `STATUS.md` 的"下一步"开始新的有界动作

## 注意事项

- 不要补写聊天记录中没有的实验结果
- 不要假设上次动作已成功，要以文件中的证据为准
- 如果 Graph 版本号与 STATUS 中记录的不一致，说明有其他会话写入了 Graph，需要重新加载
