# AI 示教区域

本目录存放供 Agent（Codex、Claude 或其他编码助手）按需读取的示教材料。它不是人类课程，也不是插件功能清单；内容不会进入插件运行时包。

Agent 读完示教材料后，应能独立接手 DS Lite 项目、执行有界动作、并在会话中断后恢复。

## 入口

- [AGENT 示教入口](AGENT_GUIDE.md) — 核心行为准则、文件职责、工作流和恢复协议。Agent 接手项目时优先读取此文件。
- [恢复场景](agent_recovery_scenarios/) — 常见故障的具体恢复步骤：
  - [会话中断](agent_recovery_scenarios/session_interrupted.md)
  - [状态丢失](agent_recovery_scenarios/state_lost.md)
  - [证据冲突](agent_recovery_scenarios/evidence_conflict.md)

## 参考资料

以下旧课程材料保留供参考，不再作为主要入口：

- [快速上手示例](quickstart-20.zh.md) — 项目创建到首次实验的完整流程
- [证据审查](evidence-lab-45.zh.md) — 运行成功、证据完整、指标达标和结论可用的区别
- [分支决策](scored-branch-lab-90.zh.md) — 为什么最高分路线也可能被阻塞
- [路线语义](route-lab-30.zh.md) — `supports` 和 `rollback` 与 Active Route 的关系
- [路径可移植](path-lab-30.zh.md) — 项目外数据的安全关联方式
- [Revision 冲突](revision-lab-30.zh.md) — 陈旧写入的拒绝与重试
- [行动与反思](action-reflection-student.zh.md) — 有界动作中的假设更新与负结果保留（`--lab action-reflection`）
- [四案例对比实验](matched-control-pilot.zh.md) — 普通 Codex、单文件记忆与 DS Lite 的对比

教学 fixture 只能说明协议如何工作，不能证明某个科研方法有效，也不能作为插件稳定版发布的唯一证据。