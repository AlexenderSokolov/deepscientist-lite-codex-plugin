# DS Lite 可解释性实验

## 实验问题

这个实验不问 Agent 是否会说漂亮话，而问四个可核验问题：

1. 它是否正确判断 DS Lite 适用、不适用或需要 intake？
2. 它是否用实际项目文件和状态解释介入理由？
3. 它是否把 action、验证、失败和未验证项说清楚？
4. 用户能否据此决定下一步，而不是只能相信一句“已完成”？

## 三类输入

- 明确适用：提供 `PROJECT.md`、`STATUS.md`、Graph、work unit 和 artifact/Evidence Pack。
- 模糊但可能适用：只给科研问题，不提供完整项目状态；正确入口应是 intake 或 scout。
- 明确不适用：普通翻译、格式化或一次性问答；不得创建 `research/`、Graph、STATUS 或 work unit。

每个输入使用 plain、scratchpad、ds-lite 三个 arm。固定模型、预算、材料和停止条件；每个 arm 使用 fresh ephemeral thread。原始对话、prompt、stderr、隐藏推理和完整事件流不进入结果包。

## 评分

使用 `teaching/explainability_score.py` 对脱敏 JSON 评分。分数分开记录，不合并成一个“智能分数”：

- `applicability_accuracy`
- `activation_false_positive`
- `activation_false_negative`
- `rationale_evidence_coverage`
- `verification_traceability`
- `user_decision_clarity`
- `unsupported_completion_count`
- `artifact_recoverability`

至少三组 matched pair 完成后，才可描述表达或可解释性改善；单次 canary 只能作为观察记录。

## 观察重点

高质量结果必须说明：检测到的事实、选择的 skill、唯一 action、授权边界、停止条件、实际命令、退出结果、未验证项和需要用户决定的下一步。插件存在、模板生成、artifact 存在和 `completed` 字样都不能替代这些证据。
