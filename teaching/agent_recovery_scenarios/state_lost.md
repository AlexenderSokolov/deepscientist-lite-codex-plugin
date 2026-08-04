# 状态丢失恢复

> 场景：`STATUS.md` 丢失或被损坏，但 `research/state/graph.json` 仍然完好。

## 症状

- `STATUS.md` 不存在或内容损坏
- `RESEARCH_MAP.md` 可能也丢失
- Graph 文件完好

## 恢复步骤

1. **读取 Graph**：打开 `research/state/graph.json`，获取 `active_node_id`、节点列表和边列表
2. **重建 RESEARCH_MAP**：根据 Graph 的节点和边，重建 `RESEARCH_MAP.md`
3. **重建 STATUS**：根据 Graph 的 `active_node_id` 和最近 artifact，重建 `STATUS.md`
4. **验证一致性**：确认重建后的 STATUS 与 Graph 一致
5. **继续执行**：从重建后的"下一步"开始

## 注意事项

- Graph 是权威状态，STATUS 和 RESEARCH_MAP 是投影
- 如果 Graph 也丢失，项目需要从头开始，但旧 artifact 可以作为参考
- 重建时不要添加 Graph 中不存在的信息
