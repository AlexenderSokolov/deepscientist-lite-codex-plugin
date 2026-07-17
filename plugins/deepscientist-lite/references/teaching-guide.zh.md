# DeepScientist Lite 教学说明

## 一句话定位

DeepScientist Lite 是一个用项目文件完成科研交接的 Codex 插件，不是另一个完整平台。给新用户解释时，先讲它解决的三个问题：换会话怎样接手、实验证据怎样复核、失败和分支怎样保留。

用户实际会看到：

- `PROJECT.md` 和 `STATUS.md` 负责长期目标与短期交接
- Graph 和 Research Map 负责节点、关系与当前路线
- artifact 解释每一步做了什么
- Evidence Pack 保存实验契约、日志、指标和哈希
- review 在分析前记录通过、失败或需要人工确认

它刻意不做完整平台能力：

- 不启动 daemon
- 不接 Web/TUI
- 不做 connector
- 不做 runner registry
- 不做 BenchStore
- 不把复杂调度硬编码进一个中心系统

## 讲解时必须说明的边界

Graph 记录公开状态，不记录隐藏思维链，也不为每个 revision 保存完整快照。Evidence Pack 可以发现缺文件、哈希变化和阈值未达标，但不能证明科学主张真实。Review 是独立步骤和 artifact，不代表另一模型或隔离执行环境。

Lite 插件适合：

- 入门教学
- 20-30 分钟演示
- 45 分钟证据链实验
- 90 分钟评分分支实验
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

## 给新用户的一句话

可以这样描述：

> 它不会替你做研究，而是把目标、路线、实验和审查结果留在项目里，让下一次会话或另一位同学接得上。

## 推荐演示顺序

1. 先让用户从 PROJECT、STATUS、Map 和 artifact 恢复一个现成小项目。
2. 再用 `ds-lite-intake` 启动用户自己的问题。
3. 用 `ds-lite-scout` 和 `ds-lite-idea` 说明证据与候选路线。
4. 用 `ds-lite-experiment` 对比“运行成功”和“证据完整”。
5. 用 `ds-lite-review` 对比 clean、tampered 和 threshold-miss。
6. 最后展示 experiment→review→analysis 路径，并说明被阻塞路线仍然保留。

仓库教学区提供20/30/45/90分钟课程和统一 runner；运行时 reference 只保留上述讲解边界，不携带整套课件。
