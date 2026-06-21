# 现场演示脚本

## 准备

确认插件已安装，并且新线程能看到 `$ds-lite-*` skills。

## Demo 1：新项目 intake

让 Codex 使用 `$ds-lite-intake` 从一句研究问题建立项目文件。检查 `PROJECT.md`、`STATUS.md`、`research/state/graph.json` 和 `RESEARCH_MAP.md`。

## Demo 2：旧项目接入

让 Codex 读取一个已有代码项目，做 intake-audit。重点展示：不覆盖已有结论，只补齐状态协议和缺失证据。

## Demo 3：实验记录

让 Codex 用 `$ds-lite-experiment` 记录一次小实验。重点展示 hypothesis、baseline、metric、budget、seed、failure interpretation。

## Demo 4：回溯

运行：

```bash
python path/to/ds_lite_state.py trace --root . --format markdown
```

展示当前路线如何从 intake 走到 analysis。
