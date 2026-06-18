# DeepScientist Lite 教学说明

## 一句话定位

DeepScientist Lite 是“DeepScientist 的教学/轻量内核”，不是另一个完整平台。

它保留完整系统最重要的科研协议：

- 每个项目有长期记忆
- 每个阶段有明确产物
- 每个产物挂到 Research Map
- 每条路线可以回溯
- 每次实验要能复现

它刻意不做完整平台能力：

- 不启动 daemon
- 不接 Web/TUI
- 不做 connector
- 不做 runner registry
- 不做 BenchStore
- 不把复杂调度硬编码进一个中心系统

## 和完整 DeepScientist 的关系

完整 DeepScientist 适合长期运行、可视化、多入口、多 runner、本地部署和更复杂的自动化科研任务。

Lite 插件适合：

- 入门教学
- 20-30 分钟演示
- 快速解释 DeepScientist 的核心机制
- 在 Codex 项目模式中建立科研工作流
- 不想安装完整平台但想使用核心协议的用户

## 邻接表为什么合适

科研探索天然不是线性流程。一个 idea 可能分裂成多个候选路线，一个实验失败后可能回滚到旧假设，一个分析结论可能支持或推翻某条路线。

邻接表足够轻：

- JSON 文件即可保存
- Git diff 清楚
- Markdown 可以渲染
- 不需要数据库
- 教学时容易讲明白

同时它比纯 Markdown 更稳：

- 节点状态可校验
- artifact 可追踪
- 活跃节点可恢复
- rollback route 可计算

## 给师兄沟通版

可以这样描述：

> 我们把 DeepScientist 拆成两层：完整平台负责长期运行和可视化，Lite 插件负责教学和核心协议。Lite 不追求复刻 daemon，而是把 DeepScientist 最核心的研究方法压缩成 Codex skills、文件模板和一个邻接表状态内核。这样学生可以先理解 Research Map、artifact-first、阶段推进和回溯路线，再决定是否进入完整平台。

## 演示顺序

1. 用一句研究问题触发 `ds-lite-intake`
2. 生成 `PROJECT.md`、`STATUS.md`、`research/state/graph.json`
3. 用 `ds-lite-scout` 形成 baseline/metric artifact
4. 用 `ds-lite-idea` 建立 2-3 个分支
5. 用 `ds-lite-experiment` 记录一次成功或失败实验
6. 渲染 `RESEARCH_MAP.md`，展示路径回溯和 artifact 追踪

