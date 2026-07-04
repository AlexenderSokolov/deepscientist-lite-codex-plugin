# 90 分钟评分分支实验

## 场景和学习目标

同一个 idea 产生三条路线：A 的 early score 最好但最终退化；B 提升较小但最终稳定；C 分数最高，却读取了规定中禁止使用的测试标签。

课程不要求训练模型。所有数值都是确定性 fixture，目的是练习如何把性能、证据和规范放在同一张决策表里。

学完后，学生应能保留未选路线、阻塞违规高分，并让 analysis 只从通过的 review 推进。

## 0–10分钟：准备项目

```bash
python teaching/lab_runner.py --lab branches --mode student --output .validation-tmp/branches-student
```

打开 `project/research/policy.json`，确认 `inputs/test_labels.json` 只能用于评估，不能作为候选分支输入。

## 10–25分钟：读契约，不先看分数选答案

三条路线共享 final score 0.75 的阈值和相同预算。检查三个 contract、manifest 和 experiment artifact，填写：

| 分支 | early | final | strict verify | 输入合规 |
| --- | ---: | ---: | --- | --- |
| A | 0.82 | 0.68 | 待填 | 待填 |
| B | 0.76 | 0.79 | 待填 | 待填 |
| C | 0.91 | 0.93 | 待填 | 待填 |

注意：Evidence Pack 可以检查 C 的输入文件是否存在、哈希是否一致，但不会自动理解 `policy.json` 的科研规范。这个判断属于 review。

## 25–50分钟：三组交叉审查

每组负责一条路线，在项目目录中使用：

```text
$ds-lite-review 请审查分配给我的 branch experiment。除了 Evidence Pack verify，还必须读取 research/policy.json，并检查 contract 的 inputs。给出四通道状态、总决定和最小补充检查。不得因为分数最高而忽略规范失败。
```

完成后交换审查记录。接收组必须指出原审查中一项有证据的判断和一项可能过度推断的判断。

## 50–68分钟：决定推进路线

全班回答：

1. A 的 early score 是否足以覆盖 final score 退化？
2. C 的 Evidence Pack 完整，为什么仍不能通过？
3. B 的提升不最大，为什么可能最值得继续？
4. 未选的 A、C 应该删除、覆盖，还是保留并标记状态？

选择路线后，让 Codex只从通过的 review 建立 analysis。A 和 C 保留在 Graph 中。

## 68–80分钟：一段式 Codex 挑战

在新的 student 工作区发送：

```text
请独立完成这个三分支 DS Lite 教学项目：读取项目合同、policy、三个实验契约和 Evidence Pack；分别 review A/B/C；选择一条路线进入 analysis；保留失败和违规路线。最终给出一张包含 early、final、完整性、合规性和决定的表，并说明为什么最高分不一定胜出。所有 Graph 写入必须通过 CLI。
```

学生按评分表审计 Codex 的结果，而不是只看它最后选了谁。

## 80–90分钟：参考答案与复盘

```bash
python teaching/lab_runner.py --lab branches --mode reference --output .validation-tmp/branches-answer
```

参考路线选择 B。A 因 final score 未达阈值失败；C 因禁止输入失败。这里不是在证明 B 适用于真实任务，而是在证明决策不能被单一高分替代。

## 常见错误与提交物

- 只比较 final score，漏掉 C 的输入违规。
- 因 A 前期好看而把最终退化写成成功。
- 删除未选分支，导致无法解释选择过程。
- 让 analysis 直接挂在 experiment，而不是通过 review。

提交三个 review artifact、一张比较表、一条选中路线、选择理由和至少一个回滚条件。
