# 30分钟路线语义实验：哪条边算“走过的路线”

## 前置条件和目标

先完成快速体验。目标是理解 progression route 只沿 `next`、`branch`、`supersedes`；`supports` 和 `rollback` 有用，但不会制造 Active Route 捷径。

## 0–8分钟：准备与观察

```bash
python teaching/lab_runner.py --lab route --mode student --output .validation-tmp/route-student
```

打开 `progression-trace.json`、`all-edges-trace.json` 和 `project/RESEARCH_MAP.md`。前者应经过 intake、scout、idea、decision；all 模式可以沿 supports 直接到 decision。

## 8–18分钟：解释差异

回答：如果 supports 也参与 Active Route，哪段真实推进历史会被跳过？如果 rollback 回边参与最短路，路线可能出现什么误解？

Graph 记录公开状态和关系，不是不可变思维快照，也不能“还原模型的完整推理链”。

## 18–25分钟：一段式 Codex 挑战

```text
请审计当前 DS Lite Graph 的路线语义。分别运行 progression 和 all 模式 trace，解释 next、supports、rollback 三类边的作用。不得把 revision 描述成完整历史快照，也不得声称 Graph 保存了隐藏推理链。
```

## 25–30分钟：提交与答案

提交两条 route、一段差异解释和一个“错误地把 supports 纳入 Active Route”的反例。教师重点检查学生是否把“证据关系”和“推进关系”混为一谈。

参考模式：

```bash
python teaching/lab_runner.py --lab route --mode reference --output .validation-tmp/route-answer
```
