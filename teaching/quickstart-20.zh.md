# 20分钟快速体验：换会话后还能接着做吗

## 前置条件和目标

只需要 Python 3.10+；安装插件后还可以让 Codex接手。学完后，你应能解释 PROJECT、STATUS、Graph/Research Map 和 artifact 的不同职责。

## 0–5分钟：生成工作区

```bash
python teaching/lab_runner.py --lab quickstart --mode student --output .validation-tmp/quickstart-student
```

若目录已经存在，runner 会拒绝覆盖。换一个新路径即可，不要删除旧结果。

## 5–12分钟：从文件恢复项目

不要看当前聊天记录，只打开：

1. `project/PROJECT.md`；
2. `project/STATUS.md`；
3. `project/RESEARCH_MAP.md`；
4. `project/research/artifacts/` 下两个文件。

写下项目目标、当前活跃节点、已经完成的两步和下一步建议。再检查 `research/state/graph.json` 的 `active_node_id` 是否与地图一致。

## 12–17分钟：让 Codex 接手

```text
$ds-lite-intake 请接手当前已有项目。只根据 PROJECT、STATUS、Graph、Research Map 和 active artifact 回答：项目目标是什么、当前在哪个节点、已有证据是什么、下一步应做什么。不要补写文件中没有的实验结果。
```

把 Codex 回答与自己的记录逐项对照。出现差异时，以机器 Graph 和实际 artifact 为依据，不以聊天语气为依据。

## 17–20分钟：检查理解

- PROJECT 为什么不应该每次实验都重写？
- STATUS 为什么不能替代完整历史？
- Research Map stale 时为什么应该从 Graph 重建？
- Artifact 和聊天总结有什么不同？

提交一张“四类文件—负责问题—更新时机”表。教师讲解重点：初始化只建立结构，不等于研究已经完成。
