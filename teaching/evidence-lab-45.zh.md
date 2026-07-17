# 45 分钟证据链实验

## 这节课解决什么困惑

一条命令正常结束，只说明进程没有报错。它没有回答输出后来是否被修改、指标是否达到预先阈值，也没有回答实验能否支持论文里的那句话。

本课让学生比较三个几乎相同的工作区：干净证据、被修改的输出、文件完整但阈值未达到。

## 前置条件与学习目标

- 已完成20分钟快速体验，知道 PROJECT、STATUS、Graph 和 artifact 的作用。
- 本仓库可运行 Python 3.10+。
- 学完后能独立区分：进程成功、证据完整、契约达标、review 通过。

## 0–8分钟：准备三个现场

```bash
python teaching/lab_runner.py --lab evidence --mode student --case clean --output .validation-tmp/evidence-clean
python teaching/lab_runner.py --lab evidence --mode student --case tampered --output .validation-tmp/evidence-tampered
python teaching/lab_runner.py --lab evidence --mode student --case threshold-miss --output .validation-tmp/evidence-threshold
```

每个工作区的项目都在 `project/`。先不要运行 reference 模式。

## 8–20分钟：只看事实，不先猜结论

依次检查：

1. `contract-evidence-demo.json`：预先阈值是否为 0.80？
2. `project/research/evidence/evidence-demo/manifest.json`：verification 状态和错误是什么？
3. `project/research/results/metrics.json`：实际 accuracy 是多少？
4. `project/research/artifacts/experiment-evidence-demo.md`：说明是否与实际文件一致？
5. `lab-result.json`：确定性 runner 观察到了什么退出码？

预期现象：clean 的严格校验通过；tampered 报哈希变化；threshold-miss 的哈希可以完整，但严格校验因阈值警告失败。

## 20–32分钟：完成四通道审查

在每个 `project/` 中分别交给 Codex：

```text
$ds-lite-review 请审查当前 experiment。先运行确定性 Evidence Pack verify，再分别判断：
1. 文件完整性和可复现性；
2. 契约与指标是否满足；
3. 引用是否真实；
4. 方法说明是否与代码、日志和结果一致。
每项只能写 pass、fail、needs-human 或 not-applicable。不要改写实验文件来制造通过结果。
```

把三份判断填入[学生工作表](student-worksheet.zh.md)。

## 32–40分钟：一段式 Codex 挑战

另建一个 tampered 工作区，把整个任务交给 Codex：

```text
请接手这个 DS Lite 教学项目，读取 PROJECT、STATUS、Graph、实验 artifact 和 Evidence Pack。完成 review；如果证据失败，只说明失败原因和最小修复动作，不要重新生成输出、不要绕过哈希，也不要创建 analysis 节点。最后告诉我哪些判断来自确定性校验，哪些仍需要人工判断。
```

检查 Codex 是否擅自重跑或修改证据。若修改了，挑战失败。

## 40–45分钟：核对答案

教师可以在新目录运行：

```bash
python teaching/lab_runner.py --lab evidence --mode reference --case threshold-miss --output .validation-tmp/evidence-answer
```

查看 `REFERENCE_ANSWER.md` 和教师参考 review。参考答案必须带明确标签，不能复制回学生项目冒充作答。

## 常见错误与提交物

- 把 tampered 说成“指标未达标”：错误，首先是完整性失败。
- 把 threshold-miss 说成“文件损坏”：错误，文件可以完整，只是契约未通过。
- 因为退出码为0就写 analysis：错误，跳过了阈值和 review。

提交三行对照表、三份四通道判断，以及一句对“完整证据不等于真实结论”的解释。课程不会自动删除工作区。
