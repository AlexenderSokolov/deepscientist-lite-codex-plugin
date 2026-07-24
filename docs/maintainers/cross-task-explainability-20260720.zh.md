# 跨任务表现与可解释性验收记录

> 2026-07-20 update: deterministic scoring/state/delegation tests passed. Corrected isolated preflight for `cross-task-explainability-20260720-02` passed, but its single implicit canary froze at 180 seconds with redacted `rate-limit`, zero usage/tools, no terminal turn/final feedback, and unchanged workspace. The 12-case comparison and real delegation probe were not started.

## 当前状态

本轮已完成确定性评分器和协议回归测试，尚未执行新的 12-case 真实模型对照或真实子智能体委派。当前证据等级是：源码协议通过；真实跨任务表达和宿主委派仍待隔离运行。

## 已验证

- `teaching/explainability_score.py` 接受脱敏结构化输入，拒绝未知字段、敏感字段、绝对路径和路径逃逸。
- 适用、误触发、缺验证和不安全 artifact ref 测试通过。
- 空白项目中的普通 artifact 不会自动提升 evidence strength。
- `render-status` 能从公开状态重建 Mission Board 投影。
- delegation 计划验证了 parallel、单 integration owner、`nested_delegation=false`、路径互斥、审批门和 result ref 门。

## 待执行真实实验

四类任务：工程连续性、数学反例、数值科研和科研想法评价；三个 arm：plain、scratchpad、ds-lite；首批 12 个 matched cases。另做明确适用、模糊待 intake、明确不适用三类可解释性 probe。

真实 delegation 只允许一次、最多两个互斥子任务。必须观察宿主 subagent start/stop、独立 result ref、父级核验和最终状态恢复；只有 plan-only 时记录 `protocol validated; host delegation not verified`。

## 发布边界

本记录不证明正式 cache、fresh host、Hook loading、真实 delegation、tag、push 或 release readiness。旧 pilot 保持 blocked，不读取、不 resume、不删除、不回写。
