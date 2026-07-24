# 教师版：行动、反思、Hook 与反馈

## 教学目的

学生应能把哲学要求翻译成可检查行为：先交代处境，再提出假设；行动前声明反证、预算与停止条件；行动后更新假设并承担汇报责任。

## 逐步命令

准备参考工作区：

```bash
python teaching/lab_runner.py --lab action-reflection --mode reference --output .validation-tmp/action-reflection-reference
```

检查 receipt 与 Mission Board：

```bash
python plugins/deepscientist-lite/scripts/ds_lite_iteration.py verify --root .validation-tmp/action-reflection-reference/project --path research/iterations/iteration-action-reflection.json
python plugins/deepscientist-lite/scripts/ds_lite_state.py mission --root .validation-tmp/action-reflection-reference/project --format json
```

用 fake clock 的单测演示 60 秒 heartbeat，不真实等待一分钟：

```bash
python -m unittest discover -s tests -p test_pilot_runtime.py -v
```

## 预期产物

reference receipt 应为 `completed`，但被评估的长度保持假设必须是 `refuted`。`completed` 表示动作与汇报闭合，不表示假设成立。Hook 案例中 Graph 直改、递归删除和创建 tmux 容量应阻断；running iteration 的 Stop 只允许续跑一次。

## rubric

| 维度 | 0 分 | 1 分 | 2 分 |
| --- | --- | --- | --- |
| 处境与授权 | 混在推测中 | 只写部分边界 | 事实、假设、价值与授权分开 |
| 单动作边界 | 多轮继续做 | 动作单一但无停止条件 | 一个动作、预算、反证与停止条件齐全 |
| 负结果 | 删除或淡化 | 留下文字无 ref | 反例、evidence ref 与 refuted 更新一致 |
| 反思 | 心理叙事 | 有总结但无偏差 | 预期偏差、责任、边界和最小下一实验完整 |
| 用户反馈 | 只说完成 | 有文件无验证 | start / progress / end、失败层和未验证项清楚 |
| Hook 判断 | 把配置当生效 | 能识别部分规则 | 区分静态配置、helper 测试与 fresh-host not-verified |

## 常见错误

- 学生把 `completed` receipt 读成 claim support。
- 教师提前给出 `a--b`，破坏反例发现过程。
- 为演示 heartbeat 真的 sleep 60 秒，而不是使用 fake clock。
- 把 raw prompt、stderr 或完整工具参数当成“透明反馈”保存下来。
- 在未获授权时让 OpenScience 自动重试 ambiguous action。

## 答案边界

参考答案只覆盖当前确定性 fixture。一次课程不能把保留 profile 提升为已验证，也不能证明插件在 fresh Codex 宿主中自动触发或加载 Hook。

## Windows 与 WSL

Windows PowerShell 使用反斜杠也可准备课程；Git Bash/WSL 使用 POSIX 路径。评分只检查项目相对 refs。WSL probe 是标准库计算演示，不冒充 Linux 插件安装、cache 发现或跨发行版验收。

## OpenScience 主管示例

主管读取 Mission Board，批准一个有界 action，观察基层 worker 的 start 反馈和 60 秒心跳，收到终态 receipt 后核对负结果与用户报告。若状态为 partial、blocked、failed 或 ambiguous，主管决定下一轮；Lite 不创建队列、后台 worker 或自动重试。
