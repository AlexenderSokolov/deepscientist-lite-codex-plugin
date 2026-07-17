# OpenScience 调用 DS Lite worker 的轻量交接协议

本文说明当 OpenScience 或类似主管系统已经能够创建 Codex 任务时，DeepScientist Lite 应如何作为轻量 worker 协议配合。DS Lite 不接管主管角色，不启动 daemon，不提供 MCP、Web/TUI 或长期调度；它只保证每个基层 Codex worker 的目标、进度、证据、回退点和下一步可以被文件读取。

## 角色边界

| 角色 | 负责什么 | 不负责什么 |
| --- | --- | --- |
| OpenScience 主管 | 创建任务、分配预算、决定是否继续、收集多个 worker 结果 | 亲自维护每个小项目的 artifact 细节 |
| Codex worker | 读写代码、运行授权范围内的命令、分析结果、更新 DS Lite 文件 | 在无授权时长跑、安装依赖、访问外部数据 |
| DS Lite 插件 | `PROJECT.md`、Mission Board、Graph、Evidence Pack、review、单轮 iterate 协议 | daemon、队列服务、后台自动研究、科学真实性证明 |

进程生命周期始终由 OpenScience 主管、调度器、稳定用户 shell 或其他可查询的外部 owner 持有。DS Lite worker 不接管进程，只维护 `research/artifacts/external-task-<task-id>.md`、逐 attempt 的 Evidence Pack / run ID 索引、日志/checkpoint 索引和恢复证据。若启动上下文是 `agent-ephemeral` 或 `unknown`，worker 只能生成包含精确命令与查询方式的 launch-ready handoff，不得声称后台任务已经持久运行。

## tmux 容量交接

需要 tmux 时，worker 先统计并发实验和长驻 Codex CLI worker，写入 `research/artifacts/external-tmux-plan-<plan-id>.md`。计划必须说明为什么需要这些终端、固定 socket、anchor session、每个 workload pane 的任务映射、资源/调用预算、名称和容量上限，并生成一段可直接执行的用户 bootstrap 命令。

worker 随后停在 `awaiting-user-bootstrap`。用户从独立稳定 SSH shell 手动创建 tmux server、顶层 session/window/pane，detach 后按计划完成一次真实断线和重连。下一轮 worker 只能读取并核对 socket、server PID 与启动时间、UID、boot ID、cgroup/container/namespace 和 pane 坐标；指纹与 probe 一致后才把计划标为 `verified`。Codex 不得自行创建顶层 tmux、补充容量或在 socket 消失时回退到新的 server。

tmux session 本身没有父子层级，本协议不建立“tmux 子会话”对象。用户要求子会话时，worker 只能将其解释为已分配 pane 中的 pane-scoped Codex CLI child worker。worker 可以在明确授权的 pane 中执行一次 child worker 启动，但必须服从计划记录的唯一启动权，并在启动前持久化 canonical slot claim：`plan_id + slot_id + task_id + attempt + command_hash`。随后把 CLI PID、provider/version、thread/task ID、查询与恢复命令写回对应 `external-task-*`。tmux server 或 CLI 仍在，只能说明相关进程可能存活，不能单独证明 provider 对话或实验计算已经恢复。

## 最小调用流程

1. 主管创建一个隔离项目目录，并给 Codex 一个明确研究问题、预算、允许动作和停止条件。
2. Codex 使用 `$ds-lite-intake` 初始化或接入项目。
3. 主管或 Codex 读取：

   ```bash
   bash run_research.sh mission --format json
   ```

4. 如果需要推进一轮，调用 `$ds-lite-iterate`。该 skill 只允许选择一个动作：`exploit`、`branch`、`debug`、`review`、`analysis`、`stop` 或 `ask-human`。
5. 本轮结束后，worker 必须运行或等价执行：

   ```bash
   bash run_research.sh render-status
   ```

6. 主管收集 `STATUS.md`、`RESEARCH_MAP.md`、`research/artifacts/frontier-decision-*.md`、Evidence Pack manifest、review/analysis artifact，并决定是否再次创建任务。

涉及跨 SSH、工具调用或 worker 生命周期的任务时，主管还要读取 `external-task-*` 记录，并以记录中的 host、owner、PID/job、日志、退出码、heartbeat、checkpoint 和预算证据判断任务状态。恢复顺序遵循 `recover first, resubmit last`；只有证明旧进程不存在、无法恢复且不会重复消耗预算后，才允许追加新 attempt。

## Mission Board 字段用途

- `active_node_id` / `stage`：worker 当前真正停在哪里。
- `next_action`：下一步单个动作，不是长计划。
- `candidate_queue`：可分叉路线，适合主管选择或排队。
- `experiment_queue`：正在准备、运行或等待 review 的实验。
- `rollback_targets`：失败后能回到哪里。
- `metric_surfaces`：从 Evidence Pack contract 派生的指标名称、方向、阈值、预算和 early/final/aggregate 面。
- `evidence_strength`：当前路线是 planning、needs-evidence、has-evidence 还是 reviewed。
- `claim_readiness` / `evidence_detail`：typed evidence/review 是否足以支持 claim、最新 refs 和具体 blocker。
- `validation`：active route 是否干净，其他分支警告是否被保留。
- `readiness_rules`：防止把 artifact、ready、idea 或不可见状态误判成研究进展。

## 单轮 iterate 的验收

一次 `$ds-lite-iterate` 成功不等于研究完成。它只表示本轮 worker 至少留下：

- 一个 frontier decision artifact；
- 一个 graph 节点或边的明确变化，或一个清楚的 `stop` / `ask-human` 决定；
- 更新后的 `STATUS.md` Mission Board；
- 若涉及实验，则有 contract、预算、metric direction、失败解释和 Evidence Pack 状态；
- 若涉及结论提升，则先通过 review。

## AIResearch 经验固化

AIResearch 暴露过几类失败：后端状态存在但用户看不见、idea line 被误当成实验推进、API ready 被误当成任务完成、simple regret 方向错误没有及时作为协议失败暴露、v2/v3 tradeoff 没有自然推进到 adaptive v4。

DS Lite worker 因此必须遵守：

- artifact 不是进度；进度必须出现在 Mission Board。
- ready 不是完成；完成必须有证据链和下一步/停止理由。
- idea 不是实验；没有 smoke/default/review/analysis 时只能说“准备实验”。
- metric wrong 是协议失败；必须记录 correction 和 superseded/rollback 关系。
- 没有可见闭环就没有智能体体验；每轮必须能回答“刚做了什么、为什么、下一步是什么、能回到哪里”。
