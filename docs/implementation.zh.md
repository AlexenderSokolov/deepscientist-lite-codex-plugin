# DeepScientist Lite 实现说明

这份文档解释插件是怎么实现的。它不是 README，也不是宣传稿，而是给维护者、师兄和后续开发者看的实现说明。

## 1. 实现目标

DeepScientist Lite 的目标是把完整 DeepScientist 中最适合教学和快速上手的部分抽出来，做成一个轻量 Codex 插件。它不部署 DeepScientist daemon，不下载本地模型，不声明 MCP、apps 或 hooks，也不提供 Web/TUI。它只提供一套文件化科研协议，让 Codex 能按阶段推进、记录证据、保留失败、回溯路线。

插件本身是主产品。实验项目只是验证插件流程和做教学演示的案例，不是插件的核心交付。

## 2. 插件包结构

安装用插件位于：

```text
plugins/deepscientist-lite/
```

关键组成是：

- `.codex-plugin/plugin.json`：Codex 插件 manifest。
- `skills/`：五个可触发的 Codex skills。
- `scripts/ds_lite_state.py`：无依赖状态图脚本。
- `assets/templates/`：项目文件模板。
- `references/`：skills 需要读取的协议说明和模板。

仓库根目录的 `teaching/`、`docs/`、`tools/` 不属于插件运行时。它们分别用于教学、维护说明和仓库验证。

## 3. Manifest 设计

`plugin.json` 只声明 `skills: "./skills/"`，不声明 `mcpServers`、`apps`、`hooks`。

这样设计有三个原因：

1. 保持轻量，避免用户误以为它会启动完整平台。
2. 让教学重点落在科研协议，而不是部署复杂度。
3. 让插件可以直接从 Codex marketplace 布局安装和验证。

## 4. Skills 设计

插件提供五个 skills，对应一个最小科研闭环：

- `ds-lite-intake`：新项目启动或旧项目接入，建立 `PROJECT.md`、`STATUS.md`、`RESEARCH_MAP.md` 和状态图。
- `ds-lite-scout`：澄清问题，初筛文献、baseline、benchmark、数据和风险。
- `ds-lite-idea`：形成候选想法，选择可验证路线。
- `ds-lite-experiment`：实现、运行或记录实验，要求写清 hypothesis、baseline、metric、budget、seed 和 failure interpretation。
- `ds-lite-analysis-write`：把证据整理成 claim table、阶段总结或写作草稿，明确区分 early/final budget 和负结果。

每个 `SKILL.md` 的 frontmatter 只允许 `name` 和 `description`。复杂约束放在正文里，方便 Codex 触发，也方便教学解释。

## 5. 状态图内核

`ds_lite_state.py` 是一个无依赖 Python 脚本，用邻接表管理科研路线。

机器可读权威状态是：

```text
research/state/graph.json
```

人类可读投影是：

```text
RESEARCH_MAP.md
```

核心 JSON 结构是：

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

节点记录公开摘要、状态、artifact 路径、memory 路径和 evidence 路径。边记录 `next`、`branch`、`supports`、`blocks`、`supersedes`、`rollback` 等关系。

脚本刻意不记录隐藏 chain-of-thought，只记录可公开审计的 summary、reason、observation 和证据路径。

## 6. 文件协议

一个 DS Lite 项目通常包含：

- `PROJECT.md`：项目级长期记忆。
- `STATUS.md`：当前节点、阻塞和下一步。
- `RESEARCH_MAP.md`：研究图的人类可读投影。
- `research/state/graph.json`：机器可读状态图。
- `research/memory/*.md`：长期事实卡片。
- `research/artifacts/*.md`：idea、experiment、analysis、paper 等记录。
- `run_*.sh`：可复现实验或分析入口。

这套协议的重点不是替用户“想完所有问题”，而是让每一步都可恢复、可检查、可教学。

## 7. 教学区分离

`teaching/` 是独立教学区，放课堂讲解、演示脚本和脱敏案例。它不进入插件运行时路径。

这样做是为了防止主次混乱：插件是产品，实验和案例只是说明插件为什么有用。案例可以更新，但不应该成为插件发布的硬依赖。

## 8. 脱敏策略

发布材料应避免包含：

- 本机绝对路径；
- Windows 用户名；
- 具体私有硬件信息；
- 访问凭据或密钥示例；
- 私有仓库状态；
- 未经验证的夸大实验结论。

案例使用通用名称，例如 “paradigm-comparison teaching project”。实验结论只作为教学示例，不包装成插件自身能力。

## 9. 验证工具

验证工具已移到：

```text
tools/validation/
```

推荐运行：

```bash
python tools/validation/validate_repo.py
```

它会检查 manifest、skill frontmatter、TODO 残留，并创建临时 smoke project 测试状态脚本。

`run_validate.sh` 和 `run_validate.ps1` 只是可选包装脚本，所以放在 `tools/validation/`，不再放在仓库根目录。
