# 现场演示脚本

## 准备

确认插件已安装，并且新线程能看到 `$ds-lite-*` skills。准备一个空目录或一个很小的已有项目作为演示对象。

## Demo 1：新项目 intake

让 Codex 使用 `$ds-lite-intake` 从一句研究问题建立项目文件。演示时重点打开：

- `PROJECT.md`
- `STATUS.md`
- `research/state/graph.json`
- `RESEARCH_MAP.md`

要讲清楚：这些文件共同回答“项目是什么、现在到哪一步、下一步做什么”。

## Demo 2：旧项目接入

让 Codex 读取一个已有代码项目，做 intake-audit。重点展示：不覆盖已有结论，只补齐状态协议和缺失证据。

## Demo 3：实验记录

让 Codex 用 `$ds-lite-experiment` 记录一次小实验。重点展示 artifact 里是否写清：hypothesis、baseline、metric、budget、seed、expected signal 和 failure interpretation。

## Demo 4：回溯路线

运行：

```bash
python path/to/ds_lite_state.py trace --root . --format markdown
```

展示当前路线如何从 intake 走到 analysis。最后强调：Lite 插件最重要的价值不是“自动得出结论”，而是让研究过程可以恢复、检查和教学。
