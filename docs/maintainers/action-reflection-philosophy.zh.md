# DeepScientist Lite 行动、反思与责任架构

## 文档状态

本文描述未发布 v0.5 源码中的最小 reflective iteration、假设池、轻量 Hook helper 和用户反馈协议。Python helper、schema、静态配置与 fake-host 行为已经可以在源码测试中验证；Codex 是否在 fresh-host 中加载 `hooks/hooks.json`、是否隐式触发九个技能，以及真实模型是否稳定遵循该流程，仍是 `not-verified`。在完成单独授权的宿主探测前，不得把“配置存在”写成“Hook 已生效”。

## 为什么需要这一层

一次长任务失败时，用户最先感受到的通常不是算法错误，而是失去方向：不知道当前在做什么、不知道哪里失败、不知道哪些判断已经改变，也不知道是否还会继续耗费时间。只有最终一句“失败了”无法支持恢复；只有频繁聊天而没有项目产物，也无法跨线程接手。

本设计把体验问题拆成五个可验证目标：

1. 插件能在新项目或已有工作区给出统一入口。
2. 每轮只执行一个带预测、反证条件、预算和停止条件的动作。
3. 动作结束后必须保存可观察结果、假设变化、负结果、责任边界和用户报告。
4. 明确违规在工具调用前阻断，状态漂移在调用后暴露，未闭合迭代在 Stop 时最多续跑一次。
5. 用户可以从 Mission Board 和实时进度投影知道当前状态，而不必读取原始事件流或隐藏推理。

## 三种哲学怎样落到工程规则

### 行动哲学

知识不是靠更长的计划自动增长，而是在具体处境中通过可反驳的行动获得。行动前先写事实与假设，再选择一个优先可逆的最小 probe；行动后用实际结果更新判断。没有预测、反证条件和停止条件的“继续探索”不是合格动作。

### 存在主义

这里不宣称模型具有意识、人格或主观体验。存在主义只作为责任视角：一个 worker 的能力不是由自我描述决定，而是由当下选择、用户授权和公开产物体现。它不能把“系统让我做的”当成越权理由，也不能用心理叙事替代可核验事实。不可逆选择必须交还真实用户。

### 反思与负责任探索

反思不是生成一段漂亮总结，更不是保存隐藏思维链。它必须回答：观察到了什么、与预测差在哪里、哪条假设被支持/削弱/反驳、哪些负结果定义了边界、是否遵守授权、还有什么义务未完成、下一个最小判别实验是什么。失败检查与反例必须保留，不能为了路线看起来顺畅而丢弃。

这三种视角被压缩为运行时《负责任探索公约》的七条行为。详细哲学留在本文，skills 只加载简洁公约，避免每轮上下文膨胀。

## 五层结构

### 1. 统一入口

第九个 `$ds-lite` skill 识别新项目或已有 DS Lite 工作区，读取 Mission Board，向用户说明插件为什么介入，然后只路由到一个现有动作 skill。它不自行执行多个阶段，不循环，也不绕过专业 skill 的证据或审批规则。

### 2. 行动公约

九个 skills 共同引用 `references/responsible-exploration-covenant.md`，使用同一个 `start / progress / end` 反馈协议：

- 开始：目标、选用 skill、唯一动作、风险和检查点。
- 过程中：关键发现、方案变化、阻塞和验证结果；长操作至少每 60 秒给一次脱敏心跳。
- 结束：实际动作、文件、验证、失败层级、未验证项、假设变化、下一动作和需要用户决定的事项。

### 3. Reflective iteration

`scripts/ds_lite_iteration.py` 提供 `ds-lite.iteration.v1` 的 `init`、`finalize` 和 `verify`：

```text
read mission
  -> register running receipt at expected revision
  -> perform exactly one action
  -> verify observable outputs
  -> record reflection and user report
  -> finalize terminal status
  -> verify receipt
  -> render STATUS
  -> stop
```

终态固定为 `completed|partial|blocked|failed|ambiguous`。`completed` 只表示这次动作、验证、反思与汇报闭合，不表示假设成立或 scientific claim 可支持。transport 结果不明或有 duplicate risk 时使用 `ambiguous` 并停止，不自动重试。

这只是最小 reflective iteration，不是 exactly-once transaction。它已有写前 revision 检查、严格 schema、新文件独占创建和 JSON 原子替换，但尚未提供 action envelope、canonical idempotency key、跨文件提交日志、重复请求复用 receipt 或 partial-write 自动修复。P1 的这些事务接口继续延期。

### 4. 轻量 Hook

`hooks/hooks.json` 和 `scripts/ds_lite_hook.py` 定义四个可独立测试的 helper：

- `UserPromptSubmit`：只在 DS Lite 工作区附加脱敏 Mission Board、证据门和建议入口，不保存原 prompt。
- `PreToolUse`：只阻断确定违规，例如直接编辑 Graph、危险 reset/clean/递归删除、自动创建或扩容 tmux、绕过 expected revision 的状态写入。
- `PostToolUse`：返回轻量一致性计数，不保存完整工具参数、输出或 stderr。
- `Stop`：发现 running iteration、缺失 reflection 或缺失 user report 时最多续跑一次；`stop_hook_active=true` 时必须放行，防止反思变成无限循环。

第一版不把 `hooks` 字段加入 manifest，因为当前仓库 validator 和目标宿主契约尚未确认该字段。若 fresh-host 不加载插件局部 Hook，产品退化为 skill 公约、iteration CLI 和 repository validator，其他能力仍可使用。

### 5. 用户进度投影

Mission Board 兼容增加 `latest_iteration` 和派生 `hypothesis_pool`。pilot runner 另提供脱敏实时投影，只显示 call 编号、case/arm/round、thread 是否建立、事件类别、工具计数、最近事件年龄、已用/剩余时间、失败类别和相对 receipt ref。它不显示 prompt、完整消息、原始 JSONL、stderr、工具参数、secret 或工作站绝对根目录。

## 假设池不是第二张状态图

Graph v2 继续是路线权威。`hypothesis_pool` 只是 Mission Board 的可重建投影，按以下来源合并：

1. Graph 中的 idea/branch 候选以 `untested` 起步。
2. Factor Card 提供候选、选择理由和最小实验，但不升级 evidence，也不把未知分数改成 0。
3. 最新合法 iteration 的 `hypothesis_updates` 覆盖显式状态，并把负结果和 evidence refs 关联回候选。
4. `next_candidates` 补充下一轮候选，不自动成为 active route。

假设状态只有 `untested|supported|weakened|refuted|inconclusive|parked`。`supported`、`weakened` 和 `refuted` 必须引用可检查 evidence refs；没有测量的候选保持 `untested`。完整负结果可以反驳或削弱假设，但不会自动把 claim 变成 `supportable`。

## Reflection 的公开边界

`reflection` 只保存：

- 可观察结果和预期偏差；
- 带 evidence refs 的假设状态更新；
- 负结果；
- 授权依据、已遵守边界和未完成义务；
- 学到的适用边界；
- 下一候选和最小判别实验。

它拒绝隐藏推理、完整对话、secret、敏感键、不安全路径、未经证据支持的心理叙事和工作站绝对根目录。`extensions` 是唯一 forward-compatible 扩展位置。

## OpenScience 主管怎样使用

OpenScience 管任务生命周期，Lite 管一次基层执行协议：

1. 主管创建或选择 work unit。
2. worker 用 `$ds-lite` 读取 Mission Board 并说明路由理由。
3. 主管批准一个单 worker 动作，或明确批准一个 `ds-lite.delegation.v1` 有界计划。
4. worker 登记 running receipt，执行一个动作并持续给出可见检查点。
5. worker 写终态 reflection、user report 和 STATUS 后停止。
6. 主管核对 evidence、负结果和失败层级，再决定是否开始下一轮。

Lite 不创建后台 worker、队列、scheduler、daemon 或无限反思循环。外部长任务仍由稳定外部 owner 管理；Hook 不能自创审批事实。

## 失败时怎样向用户负责

失败报告应先定位层级，而不是只说“命令失败”：

- precondition：输入、依赖、revision 或工作区不满足；
- authorization：缺少真实用户或主管批准；
- execution：动作已经明确失败；
- observation：结果不明，可能已执行；
- evidence/review：运行完成但不能提升结论；
- state：项目记录未闭合；
- duplication：重放存在重复风险。

报告必须给出已经确认的事实、未确认的范围、保存的相对产物、是否可能重复执行，以及下一步需要谁决定。未知根因保持未知，不用猜测填空。

## 验证门

源码层可以验证：schema 正负例、revision、原子 JSON、假设池派生、Hook 分类、Stop 单次续跑、60 秒 fake-clock heartbeat、静默/失败/ambiguous canary、九技能元数据和教学实验。

以下仍需单独授权：fresh-agent trigger forward test、Hook fresh-host probe、真实 Codex CLI canary、cache 安装、matched pilot 重跑、真实子智能体委派、tag、push 和 release。旧 `matched-pilot-20260717-01` 永久保持 blocked，不 resume、不删除 session、不回写冻结证据。
