# DeepScientist Lite 路线图与延期门

本文只记录会影响后续实现和发布判断的长期事项。临时命令、单次失败和执行流水账不写入这里。

## 当前发布线

`v0.4.0-beta.2` 发布 P0 的 work unit、typed evidence/review、Mission Board 和单轮 worker handoff。Graph v2、Evidence Pack v1、旧 CLI 与字符串 `next_action` 保持兼容。该版本可以作为 source/package prerelease 使用，但 fresh cache installation 和新线程发现仍未验证。

## 0.7 拆包候选

`0.6.0-beta.1` 单体身份已经冻结，不再增加能力。该段是历史候选记录；当前 marketplace 已拆为六个独立包，版本和兼容矩阵以 `PROJECT.md` 的 0.8 release candidate 边界为准。旧单体目录在兼容期保留，但不再作为 marketplace 目标；任何批量清理由用户另行执行。

Core 只拥有九个科研 worker 技能、Graph v2、Evidence Pack v1、iteration、delegation、handoff 和 Hook。Academic 拥有 17 个 Nature 技能；Web 只处理公开资料并记录 `ds-lite.capability.v1` / `ds-lite.source-record.v1`；Knowledge 只生成待审 `ds-lite.knowledge-proposal.v1`，不复制 Tapestry、ScholarAIO 或 ResearchKB 的正式存储职责。所有可选包必须显式检查 Core `0.8.1-beta.1`，不依赖 marketplace 传递安装。

早期四包候选的源码结构、尺寸、技能边界、版本兼容、路由冲突和固定安装矩阵由 `tools/validation/validate_packages.py` 检查。当前实现已扩展为六包和八种矩阵；它们都不是正式安装证据。拆包后的真实 Hook、真实 delegation、4-case × 3-arm matched effect、formal cache、fresh Desktop 与 release receipt 均须重新产生，不继承 `0.6.0-beta.1` 结果。

## 下一条短期线

- 领域中立 Factor Card：源码已实现 schema、validator、模板及 idea/review 规则；fresh-agent 行为仍待授权验收，不做自动加权真值或金融 DSL。
- 有界任务协调：源码已实现 `ds-lite.delegation.v1`、`$ds-lite-coordinate`、最多三个明确授权子任务、路径所有权、预算、回传和集成责任；真实子智能体 forward test 尚未授权，不提供 daemon、队列或后台 scheduler。
- 行动与反思：源码已实现第九个 `$ds-lite` 总入口、共享行动公约、最小 `ds-lite.iteration.v1`、Mission `latest_iteration` / `hypothesis_pool`、轻量 Hook helper 和脱敏进度投影。2026-07-18 E1 preflight 已验证零/九技能隔离 surface，但唯一 canary 建立 thread 后以 `rate-limit` 类别、0 token/tool、无 terminal turn/反馈和 `timeout` 结束，不能确认隐式触发。trigger forward test 与 Hook fresh-host 仍是后续授权门。
- 真实教学 pilot：静态基础设施、冻结源码、双 home、18 次串行计划、脱敏 execution receipt、fail-closed resume、公开产物评分和跨平台入口已实现。首个授权运行在第一个 plain 工程调用后 `process-failed`，0/18 completed；其余 arm 和 WSL 数值任务未执行。当前没有效果结论，该 pilot 不得 resume。

只有 12-arm 真实产物完成脱敏、统一评分并通过复核后，才讨论 `0.5.0-beta.1` 候选。单次 pilot 只提供描述性证据，不验证保留 profile，也不构成统计显著性结论。

下一次运行必须使用新 pilot id 和新输出根，固定显式 CLI，先经过不调用模型的 preflight，再只运行一次 canary。只有 canary 同时具备 completed event、最终反馈、非零 usage、工具观察、隐式 skill 证据和零工作区修改时，才可申请 trigger campaign；它仍不授权 18-call pilot。2026-07-17 与 2026-07-18 两个 pilot 均保持冻结，session/receipt 不进入新运行输入；其处置需要单独用户决定。

## 延期 P1-P3

| 门 | 延期接口 | 当前可用替代 | 发布声明 |
| --- | --- | --- | --- |
| P1 | action envelope、canonical idempotency、same-key replay、exactly-once/partial-write transaction | 最小 `ds-lite.iteration.v1` 的 revision、单动作、反思、汇报和终态 | 部分实现，不是 exactly-once |
| P2 | typed external-long profile、failure/retry/resource helper | `external-task-*` / `external-tmux-plan-*` Markdown handoff | provisional |
| P3 | cache/new-thread、真实 tmux/provider、macOS、完整跨模式矩阵 | source/package validation 与待验收清单 | not verified |

延期项不得阻塞普通 none/inline 项目的使用，但不得被默认值、示例或宣传写成已经支持。只有真实案例、可确定验证和兼容测试齐全后，才重新经过 core/profile/fixture/reject 审计。

## 长期不做

Lite 不增加 daemon、后台 scheduler、队列、MCP、Web/TUI、connector、模型路由、数据库或无限自动循环。轻量 Hook 只能附着状态、阻断确定违规和检查一次迭代，不拥有任务生命周期。外部长任务由稳定外部 owner 管理；Lite 只保存有界任务、证据、review、交接和停止理由。

## 2026-07-24 跨学科扩展候选

当前实现将上一节的“四包候选”更新为六包发布边界：Academic 升到
`0.8.1-beta.1`，新增 Empirical 与 Engineering `0.2.0-alpha.1`。两者
各只有一个 router skill，要求精确 Core `0.8.1-beta.1`，不携带运行时、
数据库或上游快照。Web/Knowledge 的按需加载和 Tapestry/ScholarAIO 伴生
边界不变。

Academic 新增引用状态、batch envelope、30/7 天终态缓存、修订约束和
adversarial review；Empirical 新增 estimand/识别/诊断/稳健性结果协议；
Engineering 新增单位/采样/FFT/随机种子/混叠/泄漏/图轴协议。对应测试和
入口分别为 `tests/test_academic_protocols.py`、`tests/test_empirical_pack.py`、
`tests/test_engineering_pack.py` 与 `run_validate_*.*`。这仍是源码和离线
协议证据，不是真实 provider 或宿主证据。

上游只以设计原子进入 `evaluation/cross-disciplinary-upstreams.json`；
commit、许可证和哈希冻结后才可复评。AI-Research 与 RDKit/Scanpy 保持
deferred，Core 苏格拉底模式等待五类真实宿主门关闭。
