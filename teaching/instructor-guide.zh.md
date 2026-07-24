# 教师指南：怎样让学生真的作出判断

## 课前检查

1. 在授课机器上运行 `python teaching/lab_runner.py --help`。
2. 用 student 模式准备课程，确认目录中没有 `REFERENCE_ANSWER.md`。
3. 新开 Codex 线程，记录实际加载版本与技能数：`0.4.0-beta.2` 发布包为七个，未发布 v0.5 源码为九个；不要从源码反推 cache。
4. 准备纯 CLI 备用路线；插件缓存失效时，课程仍可检查 Graph 和 Evidence Pack。
5. 不使用学生真实数据、凭据或未授权外部文件。

## 课堂分工

runner 负责产生相同的事实和故障；Codex负责按技能读取、检查和写 artifact；学生负责质疑 Codex 的判断。三者不能互相冒充。

若 Codex 说“通过”，追问它引用了哪个 contract、manifest、日志或 policy。若只有顺畅的文字而没有文件依据，应判为证据不足。

## 关键提问

- 这个判断是 CLI 可以确定的，还是需要人解释的？
- 如果删除聊天记录，仅靠项目文件还能复原吗？
- 结果分数和输入合规冲突时，哪条规则优先？
- blocked 节点下一步需要什么最小证据？
- 这条说明有没有把“完整性”夸大成“科学真实性”？

## 故障处理

- runner 报输出目录已存在：换新目录，不覆盖学生产物。
- Windows 找不到 Python：设置 `PYTHON_BIN`，或从 PowerShell 包装运行。
- 技能未发现：重启 Codex Desktop 并新建线程；不要因此跳过确定性 CLI 检查。
- WSL 路径慢：课程可以在 ext4 副本运行，但保留原工作区，不做批量清理。

## 参考答案怎么用

reference 模式只用于备课和课后核对。它生成的 review/analysis 带“教师参考”标记。不要把这些文件提前放进 student 工作区，也不要把 reference 模式通过说成 Codex 自动完成了科研审查。

## Matched-control pilot 怎么用

[四案例三组 pilot](matched-control-pilot.zh.md) 只用 student workspace；教师指南和 rubric 在生成包根目录独立保存。每次只打开一个 arm，工程案例分三轮投递并在第三轮更换上下文。真实 12-arm 调用前固定模型、预算、工具和计时规则并取得明确授权。首批结果只做描述性比较，不作统计显著性宣称。

## 行动与反思课程怎么用

先用 student 模式让学生写出事实、假设、预测、反证条件、预算和停止条件，再允许执行唯一 probe。检查重点不是反思文字是否漂亮，而是 `ds-lite.iteration.v1` 是否保留可观察结果、假设状态变化、负结果、授权边界和面向用户的报告。危险命令只用于 Hook 分类演示，不在课堂中实际执行；参考流程见[教师讲义](action-reflection-instructor.zh.md)。

## 收集反馈

课后请记录：学生在哪个术语停住、哪条命令无法复制、哪份文件最难理解、是否能独立解释三种 evidence case。一次课堂观察不足以改写长期规则，应积累多名新用户证据后再调整课程。
