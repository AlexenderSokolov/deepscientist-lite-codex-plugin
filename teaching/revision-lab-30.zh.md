# 30分钟 Revision 冲突实验：旧状态为什么不能强行覆盖

## 前置条件和目标

适合多会话协作或软件工程课程。目标是观察陈旧 revision 的退出码4，并练习“重读—协调—重试”，而不是手改 JSON。

## 0–8分钟：准备冲突

```bash
python teaching/lab_runner.py --lab revision --mode student --output .validation-tmp/revision-student
```

runner 模拟两个会话都读到初始 revision。会话 A 先写入；会话 B 携带旧 revision 写入时被拒绝，随后读取新 revision 并成功重试。

## 8–18分钟：还原事件顺序

查看 `lab-result.json` 中的 `initial_revision`、`stale_write_exit_code`、`reloaded_revision` 和 `final_revision`。再看 `logs/stale-revision.log` 与 `COMMANDS.md`。

回答：被拒绝的写入有没有留下半个节点？为什么永久锁文件不等于 Graph 一直被锁住？revision 检查和文件锁分别解决什么问题？

## 18–25分钟：一段式 Codex 挑战

```text
请审计这次 revision 冲突。根据 lab-result、命令日志和最终 Graph 还原两个会话的写入顺序，解释退出码4的含义，并给出安全恢复步骤。不得建议删除 graph.lock、直接编辑 graph.json 或覆盖另一会话的节点。
```

## 25–30分钟：提交与教师重点

提交事件时间线、两个保护机制的区别和安全重试步骤。教师重点检查：学生是否先重读并协调，而不是把“重试”理解为原样重复旧命令。

参考模式：

```bash
python teaching/lab_runner.py --lab revision --mode reference --output .validation-tmp/revision-answer
```
