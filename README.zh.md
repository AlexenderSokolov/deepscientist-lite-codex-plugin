# DeepScientist Lite Codex 插件

[English README](README.md) · [文档](docs/README.md) · [教学区](teaching/README.zh.md) · [插件包](plugins/deepscientist-lite/)

DeepScientist Lite 是一个轻量级 Codex 插件，用来学习和实践可回溯的科研工作流。它保留 DeepScientist 风格流程里最适合教学的部分：项目记忆、研究地图、artifact 记录、实验记录和路线回溯；但不要求用户部署完整 DeepScientist 平台。

它适合入门教学、组会演示、小型研究项目启动，以及让学生先理解“自动化科研为什么需要状态管理”。

## 它能做什么

- 为新项目或旧项目建立 `PROJECT.md`、`STATUS.md` 和 `RESEARCH_MAP.md`。
- 引导 Codex 按 intake、scout、idea、experiment、analysis/write 阶段推进。
- 把想法、实验、失败和结论记录到 `research/artifacts/`。
- 用 `research/state/graph.json` 保存轻量邻接表研究图。
- 在不启动 daemon 的情况下回溯当前研究路线。

## 它不做什么

DeepScientist Lite 不启动 daemon，不提供 Web/TUI，不安装本地模型，不暴露 MCP server，不接聊天 connector，也不替代完整 DeepScientist 平台。它是一个教学优先的插件和文件协议。

## 安装

本仓库采用 Codex marketplace 布局：`.agents/plugins/marketplace.json` 指向 `plugins/deepscientist-lite/`。

```bash
codex plugin marketplace add <owner>/deepscientist-lite-codex-plugin
```

安装或升级后，如果新线程里没有看到 `$ds-lite-*` skills，先重启 Codex Desktop，再打开一个新线程测试。

## 开始使用

在一个研究项目目录里，可以让 Codex 使用这些技能：

```text
$ds-lite-intake 从这个问题启动一个 DS Lite 研究项目：...
$ds-lite-scout 审计 baseline 和 benchmark 路线
$ds-lite-experiment 把这次实验记录进 research map
$ds-lite-analysis-write 总结证据、限制和下一步
```

如果在 Windows 命令行里直接调用 `ds_lite_state.py`，中文标题或问题建议写入 UTF-8 文本文件，再使用 `--title-file` 和 `--question-file`，避免命令行编码破坏内容。

## 仓库结构

- `plugins/deepscientist-lite/`：可安装的 Codex 插件包。
- `docs/README.md`：实现说明和维护文档索引。
- `teaching/README.zh.md`：教学材料和演示脚本。
- `tools/validation/`：维护者验证工具。
- `PACKAGE.md`：打包结构和发布边界。

## 验证仓库

维护者可以运行：

```bash
python tools/validation/validate_repo.py
```
