# DeepScientist Lite：让科研过程接得住、查得清

[English README](README.md) · [用户指南](docs/user-guide.zh.md) · [教学课程](teaching/README.zh.md) · [维护文档](docs/README.md) · [感谢名录](ACKNOWLEDGMENTS.md)

研究任务一长，聊天记录很快就不够用了：换一个会话后，不知道上次为什么选这条路线；实验跑过，却找不到当时的命令、指标和日志；一个高分结果看起来不错，但没人确认它有没有偷看测试标签。

DeepScientist Lite 用一组 Codex 技能和普通项目文件解决这些交接问题。它不替你判断科学结论；对已冻结、已授权且可审计的验收任务，它可以由前台自动控制器连续推进、自动续跑和生成进度凭证，但不创建后台 daemon。它负责把目标、路线、实验和审查结果留下来，让下一次会话或另一位同学能够接着做。

> **官方插件声明：** 这是 DeepScientist 的官方 Codex 插件。"DeepScientist"用于说明上游研究工作流和平台。详见 [NOTICE](NOTICE)。

## Skills 总览

DS Lite 共暴露 **30 个 skills**，分布在六个独立可安装的包中。

| 包 | 版本 | Skills 数 | 核心职责 |
| --- | --- | --- | --- |
| Core | `0.9.0-beta.1` | 9 | 域中性工作协议：目标保持、路线追踪、实验、证据、审查、迭代、委托、交接和有界前台自治 |
| Academic | `0.9.0-beta.1` | 17 | 17 个适配的 Nature 工作流加上有界引用、修订和对抗性审查协议 |
| Web | `0.3.0-alpha.1` | 1 | 公开网页采集和来源 provenance 记录 |
| Knowledge | `0.3.0-alpha.1` | 1 | 从 web/paper 证据生成 review-gated 知识提案 |
| Empirical | `0.3.0-alpha.1` | 1 | 有界实证研究规格、诊断和结果交接 |
| Engineering | `0.3.0-alpha.1` | 1 | 有界工程数值分析、信号处理和图形审计 |

**典型研究工作流：** `ds-lite-intake` → `ds-lite-scout` → `ds-lite-idea` → `ds-lite-experiment` → `ds-lite-review` → `ds-lite-analysis-write` → `ds-lite-iterate`

## 五分钟上手

### 1. 安装

需要 Codex 和 Python 3.10 或更高版本。插件运行脚本只使用 Python 标准库。

```bash
codex plugin marketplace add AlexenderSokolov/deepscientist-lite-codex-plugin
```

这条命令只添加插件来源。随后请在 Codex 的 `/plugins` 中选择这个 marketplace。默认只安装 `deepscientist-lite`；它在 `0.9.0-beta.1` 候选中固定为 9 个 Core 技能。论文工作流、公开网页取证、知识提案、实证分析和工程数值分析分别由五个可选包提供，按需单独安装。Academic 当前为 `0.9.0-beta.1`，Web、Knowledge、Empirical 与 Engineering 当前为 `0.3.0-alpha.1`。安装或升级后重启 Codex Desktop，并打开一个新任务核对实际插件版本和技能数；不能用源码目录反推正式 cache。

五个可选包不会假设 marketplace 自动安装 Core。首次使用前必须运行包内 doctor，显式提供 Core 根目录；缺失或版本不匹配时会停止。旧 `0.6.0-beta.1` 单体目录仍保留用于历史证据身份，但不再是 marketplace 安装目标。

### 2. 从一个真实问题开始

在你的项目目录里，把下面这段话交给 Codex：

```text
$ds-lite-intake 请从这个问题启动一个轻量研究项目：
"比较两个文本分类 baseline，在固定预算下判断哪个更值得继续。"
先检查当前目录，不要覆盖已有文件；建立项目目标、验收标准、当前状态和下一步。
```

接下来可以继续：

```text
$ds-lite 接手这个科研或工程工作区，读取 Mission Board，说明为什么插件适用。对于已批准的多门项目，它默认生成或读取 autonomy contract，并连续推进所有相互独立的 ready gate；单个 gate 冻结后继续其余 gate。只有我明确要求"只做一步""只规划"或"不要副作用"时，才只路由一个下一动作。

$ds-lite-scout 检查可用数据、baseline、指标和主要风险，给出有来源的侦察记录。

$ds-lite-idea 基于已有证据提出 2–3 条可验证路线，用 Factor Card 分开记录新颖性、可行性、证据、成本、风险和任务对齐，再选择最小有用实验。

$ds-lite-experiment 为选中的路线先写实验契约，再运行或保存可复现命令，并封装证据。

$ds-lite-review 在进入分析前检查证据包、指标、引用和方法是否对得上。

$ds-lite-analysis-write 只基于通过审查的证据总结结果、限制和下一步。

$ds-lite-iterate 读取 Mission Board，先登记 running receipt，只推进一轮有界动作，再验证、反思、汇报、更新 STATUS 并停止。

$ds-lite-coordinate 把两到三个彼此独立的任务写成有界委派计划，先停下来等明确批准，再收集、核验并由父 worker 整合结果。
```

### 3. 看懂生成的文件

第一次使用时，先看这四处：

| 位置 | 它回答的问题 |
| --- | --- |
| `PROJECT.md` | 这个项目为什么做，目标和验收标准是什么？ |
| `STATUS.md` | Mission Board：现在做到哪里、刚发生什么、下一步是什么、哪里可回退？ |
| `RESEARCH_MAP.md` | 已经走过哪些路线，当前路线如何到达？ |
| `research/artifacts/` | 每一步具体做了什么，有什么公开依据？ |

实验阶段还会看到 `research/evidence/<run-id>/`。这里保存实验契约、日志、指标、环境说明、文件哈希和验证结果。

## 它怎样帮助你

- **换会话不丢线索**：Codex 可以从项目文件恢复目标、当前节点和下一步。
- **失败也有去处**：失败实验和未选路线不会被成功结果覆盖。
- **进度看得见**：`mission` 和 `render-status` 把 Graph 投影成任务板，避免把 artifact 当成用户体验。
- **实验先约定再解释**：指标、阈值、seed、预算和失败条件在运行前写入契约。
- **高分不自动通关**：文件完整、指标达标和结论可用是三个不同判断。
- **图可以检查和重建**：机器状态保存在 `graph.json`，人读的地图可以重新渲染。
- **协作边界写得清楚**：每个子任务有独立输入、可改路径、结果路径、预算和停止条件，父 worker 负责最终核验与整合。

## 它不会替你做什么

- 不证明论文结论为真，也不保证消除错误引用或"幻觉"。
- Core 不启动 daemon、Web/TUI、MCP server、聊天 connector 或本地模型。Academic 的 MCP/API 与 Web 的托管后端都必须按工作区显式授权，不会静默修改全局配置。
- Web 包只处理公开资料，且默认 fail closed：`fetch`、`search`、`render`、`benchmark` 每次都必须显式传入一个或多个 `--allowed-domain`。初始 URL、重定向和 Firecrawl 搜索结果都会复核域名范围；不支持登录、复用 Cookie、提交表单、上传或自动安装浏览器/托管后端。
- 不在 Codex 关闭后继续运行任务。
- 不把 `$ds-lite-iterate` 变成无限自动循环；一次调用只推进一轮并停在 checkpoint。
- 不把 `$ds-lite-coordinate` 变成队列或后台 worker 服务；没有用户或 OpenScience 明确批准时只生成计划并停止。
- 不替代人工审查、领域知识、数据治理和研究伦理判断。
- Review 是一个单独的检查步骤和记录，不代表使用了另一模型或隔离执行环境。

## 遇到问题先看这里

### 新线程里找不到技能

先重启 Codex Desktop，再新建线程。旧线程可能仍使用升级前的插件缓存。

### Windows 中文参数乱码

直接调用状态 CLI 时，把较长中文写入 UTF-8 文件，再使用 `--title-file`、`--question-file`、`--summary-file` 或 `--reason-file`。

### Graph 提示 revision 冲突

不要覆盖文件，也不要手改 `graph.json`。重新读取最新状态，协调另一会话的改动，再带新的 `--expected-revision` 重试。

### 项目外数据路径被拒绝

Graph 不保存工作站绝对根目录。请使用 `external://<alias>/<relative-path>`，并通过 `DS_LITE_EXTERNAL_<ALIAS>` 提供本机根目录。

### 地图显示 stale

`graph.json` 已提交而 `RESEARCH_MAP.md` 还没同步时，运行 `render-map` 重建地图。Graph 才是机器权威状态。

## 从哪里继续

- 想理解 Graph、Evidence Pack 和 review 的设计：读[用户指南](docs/user-guide.zh.md)。
- 想亲手做一遍：从[20分钟快速体验](teaching/quickstart-20.zh.md)开始。
- 想讲课或组会演示：看[教学课程入口](teaching/README.zh.md)。
- 想比较普通 Codex、单文件记忆和 DS Lite：看[四案例 matched-control pilot](teaching/matched-control-pilot.zh.md)。
- 要升级旧 Graph v1 项目：看[迁移指南](docs/maintainers/graph-v2-migration.md)。
- 要参与维护：看[实现说明](docs/implementation.zh.md)和[仓库验证](tools/validation/)。

维护者统一验证入口：

```bash
bash tools/validation/run_validate.sh
```
