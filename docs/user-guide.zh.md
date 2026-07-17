# DeepScientist Lite 用户指南

这篇指南解释插件为什么要生成这些文件，以及它们怎样配合。若你只想尽快试用，先回到[中文 README](../README.zh.md)完成五分钟上手。

## 1. 先建立一个简单的心智模型

DeepScientist Lite 不接管科研项目。它更像一本有格式的实验台账，由 Codex 帮你维护。

每次推进都围绕四个问题：

1. 项目长期要解决什么？
2. 当前正在做哪一步？
3. 这一步留下了什么可检查的记录？
4. 下一位接手者怎样重复或质疑它？

```mermaid
flowchart LR
    P["PROJECT.md<br/>长期目标与约束"] --> S["STATUS.md<br/>当前节点与下一步"]
    S --> G["graph.json<br/>节点、关系与 revision"]
    G --> M["RESEARCH_MAP.md<br/>给人看的路线图"]
    G --> A["artifacts<br/>阶段说明"]
    A --> E["evidence<br/>契约、日志、指标与哈希"]
    E --> R["review<br/>是否允许提升结论"]
```

这些文件不是重复记录。它们的更新频率和职责不同：PROJECT 很少改，STATUS 经常改，Graph 管路线，`research/work-unit.json` 管当前有界任务，artifact 讲清一步工作，Evidence Pack 保存实验事实，review 记录检查决定；需要两到三个独立 worker 时，`delegation-*.json` 只记录授权、路径所有权、回传和父 worker 的整合责任。

`research/work-unit.json` 使用 `ds-lite.work-unit.v1`。新项目起初没有 claim requirement，所以证据状态是 planning；开始 claim-bearing experiment 前，才声明 profile、typed validator 和 canonical evidence refs。普通 Markdown、日志、PROJECT/STATUS 或任意非空路径都不是 typed evidence。schema 不认识的字段只能放进 `extensions`。

## 2. 八个技能分别在什么时候用

### Intake：先把问题和边界说清楚

`$ds-lite-intake` 用于新项目启动或旧项目接入。它会先读当前目录，再建立项目合同和初始状态。

你应当看到：`PROJECT.md`、`STATUS.md`、`research/state/graph.json` 和 `RESEARCH_MAP.md`。

它不能保证：自动理解旧项目中每个结论是否可信。旧项目接入仍需要核对 README、代码、结果和运行脚本。

### Scout：先找证据和风险，不急着拍方案

`$ds-lite-scout` 用于澄清数据、baseline、benchmark、指标、来源和可行性。

你应当看到：一个 scout artifact，写清发现、来源、缺口和下一步。

它不能保证：仅凭二手摘要验证论文主张。无法核验时应写 `needs-human` 或明确缺证据。

### Idea：把候选路线变成可证伪的问题

`$ds-lite-idea` 通常给出 2–3 条候选路线。真正值得以后回访的候选可以成为 Graph 分支。

你应当看到：候选假设、最小实验、预期信号、失败解释和选择理由。

它不能保证：分支越多越好。Lite 的目标是留下少量可检查路线，不是自动执行完整树搜索。

#### 用 Factor Card 评价 idea，而不是只问“新不新”

`ds-lite.factor-card.v1` 把一个候选 idea 分成六项。每项使用 `null` 或 0–4 分，另存 confidence、证据路径、简短依据和不确定性：

| 分项 | 要回答的问题 | 分数方向 |
| --- | --- | --- |
| `novelty` | 与最近的已知工作相比，机制、组合、目标或证据是否真的不同？ | 越高表示差异证据越强；没有来源时必须为未知 |
| `feasibility` | 最小实现或推导能否在当前数据、权限和预算内完成？ | 越高越可行 |
| `evidence_strength` | 现在已有多少可复核、typed 或可复现证据？ | 越高表示现有证据越强 |
| `cost` | 时间、算力、数据准备、外部调用和人工审查负担多大？ | 越高表示成本越高，不是越好 |
| `risk` | 技术、科学、重复执行、授权和误解风险多大？ | 越高表示风险越高，不是越好 |
| `alignment` | 它是否直接推进当前 work unit 和 active route？ | 越高越对齐 |

插件不做加权总分，也不会把最高分自动变成赢家。选择只能是 `explore`、`verify-first`、`park`、`reject` 或 `needs-human`，并且必须写一个能改变当前判断的最小测试。这样可以保留“新但贵”“可行但证据弱”“风险高但值得先做小验证”等真实取舍。

每个进入比较的候选保存为 `research/artifacts/factor-card-<slug>.json`，然后运行：

```bash
python <plugin>/scripts/ds_lite_protocol.py validate-factor-card \
  --path research/artifacts/factor-card-<slug>.json
```

Factor Card 只是路线选择 artifact，不是实验、引用核验或 Evidence Pack。即使六项都有高分，也不能把 Mission Board 从 planning/needs-evidence 升到 has-evidence；只有 work unit 声明的 typed validator 可以完成这种升级。

### Experiment：先写契约，再运行

`$ds-lite-experiment` 在运行前声明命令、输入、指标、阈值、seed、预算、预期输出和失败解释；运行后再封装日志和结果。

你应当看到：experiment artifact、`run_*.sh` 和 `research/evidence/<run-id>/`。

初始化生成的四个 `run_*.sh` 共用 `tools/ds_lite_runtime.sh`。脚本从自身位置找到项目根目录，通过 `PYTHON_BIN` 选择 Python，通过 `DS_LITE_STATE_CLI`、`DS_LITE_EVIDENCE_CLI` 或 `DS_LITE_PLUGIN_ROOT` 找到插件脚本。它们不会扫描 Codex 缓存，也不会把某台电脑的绝对路径写入项目。换机器时只需重新设置环境变量，不要改写 Graph 或把缓存目录提交到仓库。

准备交接当前路线时使用 `validate --strict --scope active-route`。它仍会全局检查图结构、路径完整性和 revision，只把其他分支上的证据警告列到 `off_route_warnings`，不让这些警告阻断当前路线。若要审计整个项目的每条分支，继续使用默认的 `validate --strict`。失败分支必须保留，不能为了得到退出码 0 而删除。

它不能保证：进程退出码为 0 就说明结果有效。退出码只描述进程是否正常结束。

### Review：把“跑完了”和“能下结论”分开

`$ds-lite-review` 先运行确定性 Evidence Pack 校验，再检查四件事：

1. 文件是否齐全、哈希是否一致、步骤能否复现；
2. 实验是否遵守预先契约和指标口径；
3. 引用能否回到真实来源；
4. 方法说明是否与代码、日志和输出一致。

每一项只能是 `pass`、`fail`、`needs-human` 或 `not-applicable`。证据不足不是通过。

Review 会同时写人类可读的 `review-<slug>.md` 和机器可读的 `ds-lite.review-result.v1` JSON。`verdict` 只表示审查门是 pass、fail 还是 needs-human；独立的 `claim_assessment` 才表示结论是 none、inconclusive、refuted 还是 supportable。只有 review node 已 done，且 work unit、profile、Evidence Pack refs 与 digest 全部匹配时，Mission 才会显示 reviewed。Markdown-only review 不会升级。

它不能保证：审查一定由另一模型执行，也不能替代领域专家或伦理审查。

### Analysis/Write：只写证据允许写的内容

`$ds-lite-analysis-write` 从通过的 review 进入分析，整理主张、证据、限制和下一步。

你应当看到：analysis 或 write artifact，其中的结论能追溯到 review 和 Evidence Pack。

它不能保证：把失败审查换一种措辞就能绕过去。未通过的路线只能写限制或补充实验计划。

### Iterate：只推进一轮，然后停在 checkpoint

`$ds-lite-iterate` 用于 OpenScience 或用户希望 worker 自主推进一个小步时。它先读取 Mission Board，再从 `exploit`、`branch`、`debug`、`review`、`analysis`、`stop`、`ask-human` 中选择一个动作。

你应当看到：`frontier-decision-*.md`、必要的 Graph 变化，以及由 `render-status` 更新的 `STATUS.md`。

它不能保证：后台持续运行。一次调用只推进一轮；GPU、长跑、依赖安装或外部数据访问仍需要用户或主管系统授权。

### Coordinate：先划清任务和写入边界，再决定是否委派

`$ds-lite-coordinate` 只适合一个 work unit 中已经存在两到三个彼此独立的有界任务。它先创建 `ds-lite.delegation.v1` sidecar，逐项写明目标、必需输入、允许修改路径、预期结果、验证命令、资源预算和停止条件，并指定唯一的父级 integration owner。

计划生成后先运行：

```bash
python <plugin>/scripts/ds_lite_protocol.py validate-delegation \
  --path research/artifacts/delegation-<id>.json
```

此时仍不能启动子任务。只有用户或 OpenScience 主管明确批准，并留下简短、项目相对的 approval ref 后，才可以使用宿主已有的子智能体能力。最多三个任务；`nested_delegation=false`；parallel 模式要求所有写入和结果路径互不重叠。子任务只回传自己的 artifact/result ref，父 worker 负责检查 diff、核验证据、运行完整测试和最终整合。

若任务只需要一个 worker、彼此依赖、共享写入路径，或父 worker 无法独立验收，就不要委派，继续使用普通 skill 或 `$ds-lite-iterate`。partial、blocked、cancelled 和 transport 状态不明都要保留，不能自动重试或启动替代任务。

它不能保证：后台排队、长期调度、自动恢复或“子智能体说完成了就算完成”。委派协议只管理一次有界计划和回传；真实效果仍需要在具体宿主和新线程中单独验收。

## 3. Mission Board 是什么

`mission --format json|markdown` 会从 Graph、artifact、Evidence Pack 和验证结果派生出一个任务板。`render-status` 会把同样的信息写进 `STATUS.md`，让用户或上层系统不用读完整 JSON 图也能知道当前状态。

Mission Board 重点回答：

- 当前研究问题和 active node 是什么；
- 最近真正完成了什么；
- 下一步单个动作是什么；
- 哪些候选路线还在队列里；
- 哪些实验等待证据或 review；
- 失败时可以回到哪个 rollback target；
- 指标方向、early/final/aggregate/AUC 等指标面是否已经在契约中说清；
- 当前证据强度是 planning、needs-evidence、has-evidence 还是 reviewed；
- 当前 `claim_readiness` 是 none、blocked、inconclusive、refuted 还是 supportable，以及 `evidence_detail` 中的 validated/negative evidence、typed review 数量、最新 refs 和 blocking reasons；
- 是否需要用户或 OpenScience 主管决策。

`waiting_for_user` 只看当前 active route、当前路线的 blocker、typed needs-human review 或 blocked work unit。off-route blocked 节点和 `off_route_warnings` 仍会显示为保留债务，但不会因为存在就无条件卡住当前路线。

它还会显示几条硬规则：artifact 不是进度，ready 不是完成，idea 不是实验，metric 错误是协议失败，没有可见闭环就没有智能体体验。

## 4. Graph 到底保存什么

`research/state/graph.json` 保存公开的研究状态：节点、边、当前活跃节点和文件路径。它不保存隐藏思维链，也不保存每次 revision 的完整快照。

常用节点包括 intake、scout、idea、experiment、review、analysis 和 decision。常用关系包括：

| 关系 | 用途 |
| --- | --- |
| `next` | 正常推进到下一阶段 |
| `branch` | 保存以后可能回访的候选路线 |
| `supports` | 说明某份证据支持另一个节点 |
| `blocks` | 说明证据缺口或依赖阻止推进 |
| `supersedes` | 新证据替代旧路线，但旧节点保留 |
| `rollback` | 记录失败后返回哪个历史节点 |

Active Route 默认只沿 `next`、`branch` 和 `supersedes`。因此，`supports` 捷径和 `rollback` 回边不会把当前路线缩短成一条误导性的路径。

## 5. Revision 和事务写入解决什么问题

两个 Codex 会话可能同时读到 revision 7。会话 A 先提交后，Graph 变成 revision 8；会话 B 再携带 `--expected-revision 7` 写入时，CLI 会以退出码 4 拒绝。

正确处理方式是：

1. 停止当前写入；
2. 重新读取 Graph、STATUS 和相关 artifact；
3. 判断另一会话改了什么；
4. 协调自己的节点、状态或边；
5. 携带最新 revision 重试。

Graph 写入还会经过跨平台锁、完整语义校验、临时文件落盘和同盘原子替换。它能降低并发覆盖和半写文件风险，但不能让 Graph、STATUS、artifact 和 Markdown 地图在多个文件之间成为一个数据库事务。

如果 Graph 已提交而地图未更新，`status` 或 `validate` 会报告 stale；`render-map` 可以修复地图。

## 6. Artifact 与 Evidence Pack 有什么区别

Artifact 是给人读的阶段记录，例如为什么做这个实验、结果意味着什么、下一步怎么选。

Evidence Pack 是机器可复核的实验记录：

- `contract.json`：运行前承诺；
- `stdout.log`、`stderr.log`：运行输出；
- `metrics.json`：结构化指标；
- 环境说明：只允许安全字段，不转储完整环境变量；
- `manifest.json`：状态、路径、大小、SHA-256 和校验结果。

一个失败进程也可以有完整 Evidence Pack，因为“实验失败”与“证据损坏”不是同一回事。反过来，一个高分结果如果哈希变化、指标口径不符或使用了禁止输入，也不能进入通过状态。

## 7. 项目内路径和外部数据

Graph 只保存两类路径：

- 项目内 POSIX 相对路径，例如 `research/results/metrics.json`；
- 外部符号路径，例如 `external://dataset/train.csv`。

本机外部根目录由环境变量提供：

```text
DS_LITE_EXTERNAL_DATASET=D:\Data\my-dataset
```

另一台机器可以把同一别名映射到 `/data/my-dataset`。Graph 中不会出现两台机器不同的绝对根目录。

外部文件默认不计算哈希，只有明确使用 `--hash-external` 时才会读取和哈希。这样可以避免插件在不知情时扫描大型数据集或未授权资源。

## 8. 换一个会话后怎样恢复

新会话按这个顺序读取：

1. `PROJECT.md`：长期目标、限制和验收标准；
2. `STATUS.md`：当前节点、阻塞和下一步；
3. Graph 的 `active_node_id` 和 Active Route；
4. 活跃节点关联的 artifact；
5. 对应 Evidence Pack、review 和 `run_*.sh`。

### 会话恢复不等于进程恢复

对话、Codex worker、tmux、实验进程和落盘工件各有独立生命周期。若存在 `research/artifacts/external-task-*.md`，恢复时固定按以下顺序核对：

1. 先读取关联的 external-tmux-plan，再读取 external-task artifact、attempt 和 Evidence Pack / run ID 索引；
2. 核对 runtime owner、host、user、node、容器/cgroup 和 tmux socket；
3. 查询 scheduler job、tmux server 和 PID，不能只看 pane；
4. 检查退出码、日志尾部、heartbeat、checkpoint、预算、产物和哈希；
5. 将任务分类为 `running`、`suspect`、`interrupted`、`completed` 或 `failed`；attempt 失败但仍可能恢复/重试时应保持 `interrupted` 或转为 `recovering`，只有明确不再重试才把任务关闭为 `failed`；
6. 修复前保留旧 attempt、对应 Evidence Pack、部分日志、配置和 checkpoint；
7. 遵循 `recover first, resubmit last`，仅在旧任务已证明不存在、恢复不可行且不会重复消耗预算时追加新 attempt；
8. 更新 external-task artifact、Graph/STATUS 和 Evidence Pack，然后停止本轮。

`nohup`、`disown`、`setsid` 或自动创建 tmux 都不能单独证明任务能够跨越临时 shell、cgroup、容器或计算节点继续运行。

恢复成功的最低标准不是“读过文件”，而是能够回答：

- 项目要解决什么？
- 当前证据是什么？
- 为什么走到这个节点？
- 哪些结论还不能说？
- 下一条可以执行的命令是什么？

### 用户手动创建 tmux

长任务需要 tmux 时，Codex 不能直接在自己的临时 shell 中创建。它先写 `research/artifacts/external-tmux-plan-<plan-id>.md`，计算需要的并发 workload pane 数量、固定 socket、session/window/pane 名称、任务映射、资源预算和安全余量，再给出一段精确的用户 bootstrap 命令及其 SHA-256。

用户从独立稳定 SSH shell 手动运行命令，创建 tmux server、anchor session 和计划内终端，然后 detach、断开并重新连接。Codex 下一轮只做身份核对和 persistence probe；只有 server 指纹、socket 和计划槽位保持一致，计划才是 `verified`。未经验证时，Codex 只能继续等待或重新出具计划，不能自己补建 session。

本协议不建立“tmux 子会话”对象。用户要求子会话时，Codex 只能将它解释为已分配 pane 中的 pane-scoped Codex CLI child worker。必须记录 CLI PID、精确 provider/model 版本、thread/task ID、查询命令和实际验证过的恢复命令。tmux 保留了 pane，并不自动保证 provider 对话、认证连接或实验进程仍然有效。

## 9. 一条完整但不夸大的路线

```text
intake → scout → idea → experiment → review → analysis
```

这条路线表示：问题已经定义，资料和基线已检查，候选路线已选择，实验已经留下证据，审查允许提升结论，最后才进入分析。

`coordinate` 不属于这条科研语义路线中的新阶段。它只是当某一步确实可以拆成二到三个独立任务时采用的执行协议，不能绕过 experiment、Evidence Pack 或 review。

它不表示每个研究项目都必须线性推进。你可以建立分支、保留失败、回滚到旧想法，也可以在证据不足时停在 blocked 状态。

失败审查有一个容易混淆的细节：review 节点应当是 `blocked`，但不能同时设为 active。active 应留在仍可操作的 experiment，或转到一个明确的补救节点；`STATUS.md` 再列出 blocked review 和最小补做动作。这样“不能提升结论”和“现在还能做什么”不会混成同一件事。

## 10. 下一步练习

- [20分钟快速体验](../teaching/quickstart-20.zh.md)
- [45分钟证据审查](../teaching/evidence-lab-45.zh.md)
- [90分钟分支决策](../teaching/scored-branch-lab-90.zh.md)
- [30分钟路线语义](../teaching/route-lab-30.zh.md)
- [30分钟路径可移植](../teaching/path-lab-30.zh.md)
- [30分钟 revision 冲突](../teaching/revision-lab-30.zh.md)
- [四案例三组 matched-control pilot](../teaching/matched-control-pilot.zh.md)

matched pilot 比较普通 Codex、单个 `NOTES.md` 和 DS Lite workspace。runner 只准备 12 个隔离 arm、分轮提示和空白评分面；真实运行前仍要固定模型/预算/工具并取得授权。不要把 `prepared-not-run` 当成插件效果证据。
