# DeepScientist Lite Codex 插件

DeepScientist Lite 是一个教学入门型 Codex 插件。它不部署 DeepScientist daemon，不下载本地模型，不接 Web/TUI、connector 或 MCP，而是把 DeepScientist 最容易教学和复用的内核压缩成：

- 5 个 Codex skills
- 一组项目模板
- 一个无依赖 Python 邻接表状态脚本
- 一套 artifact-first 的文件协议

目标不是替代完整 DeepScientist，而是让学生在 Codex 里理解并实践自动化科研探索的基本结构：问题进入、文献与 baseline 初筛、idea 分支、实验记录、分析写作、状态回溯。

## 插件边界

保留：

- 阶段工作流：intake、scout、idea、experiment、analysis/write
- Research Map：机器可读 `research/state/graph.json`，人类可读 `RESEARCH_MAP.md`
- 记忆卡片：`research/memory/*.md`
- 研究产物：`research/artifacts/*.md`
- 可复现实验入口：`run_*.sh`
- Git/worktree 思维：一个研究项目就是一个可回溯工作区

剔除：

- DeepScientist daemon
- Web/TUI/Canvas 运行时
- connector 和 runner registry
- BenchStore
- 完整 artifact service
- 长篇 mega-prompt

## 目录

```text
plugins/deepscientist-lite/
  .codex-plugin/plugin.json
  skills/
    ds-lite-intake/
    ds-lite-scout/
    ds-lite-idea/
    ds-lite-experiment/
    ds-lite-analysis-write/
  scripts/ds_lite_state.py
  references/
  assets/templates/
scripts/validate_repo.py
run_validate.sh
```

## 状态图

`research/state/graph.json` 是权威状态，结构为：

```json
{
  "schema_version": "ds-lite.graph.v1",
  "project": {"id": "", "title": ""},
  "root_node_id": "",
  "active_node_id": "",
  "nodes": {},
  "adjacency": {}
}
```

节点记录公开摘要、状态、artifact 路径、memory 路径和证据路径。边记录 `next`、`branch`、`supports`、`blocks`、`supersedes`、`rollback` 关系。

这个结构借鉴了 TraceableCodeAgent 的邻接表思想，但这里从零实现，且更偏科研流程：不记录隐藏 chain-of-thought，只记录可审计的公开证据。

## 快速验证

在仓库根目录运行：

```bash
bash run_validate.sh
```

Windows PowerShell 环境可运行：

```powershell
.\run_validate.ps1
```

也可以直接运行：

```bash
python scripts/validate_repo.py
```

验证会检查 plugin manifest、skill frontmatter、TODO 残留，并在系统临时目录创建一个 smoke project 测试状态脚本。

## 从 GitHub 安装测试

本仓库是 Codex marketplace 布局：根目录含 `.agents/plugins/marketplace.json` 和 `plugins/deepscientist-lite/`。

```powershell
codex plugin marketplace add AlexenderSokolov/deepscientist-lite-codex-plugin
```

若新线程只在 `.codex/.tmp/marketplaces/deepscientist-lite` 找到插件文件，但没有自动暴露 `$ds-lite-*` skills，请确认 `~/.codex/config.toml` 中存在：

```toml
[plugins."deepscientist-lite@deepscientist-lite"]
enabled = true
```

然后重新开一个 Codex 线程测试。当前 Codex CLI 版本可能只暴露 `codex plugin marketplace ...`，不暴露单独的 `codex plugin add`，因此这个配置项是判断插件是否真正启用的关键。

Windows 中文命令行参数有时会被 shell 编码破坏。遇到研究问题写入 `graph.json` 乱码时，把标题或问题放进 UTF-8 文本文件，并使用：

```powershell
python path\to\ds_lite_state.py init --root . --title-file title.txt --question-file question.txt
```
