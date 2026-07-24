# 学生版：行动与反思实验

## 学习目标

完成一个 `plan -> act -> verify -> reflect -> report -> stop` 循环，亲手区分支持样例与反例、工作失败与责任汇报、Hook 阻断与宿主授权。

## 逐步命令

Windows PowerShell 准备 student 工作区：

```powershell
python teaching\lab_runner.py --lab action-reflection --mode student --output .validation-tmp\action-reflection-student
```

Git Bash 或 WSL：

```bash
python3 teaching/lab_runner.py --lab action-reflection --mode student --output .validation-tmp/action-reflection-student
```

进入生成目录后，先读 `project/PROJECT.md`、`project/STATUS.md`、两个 idea artifact、`action-contract-length.json` 和 `hook-cases.json`。在 Codex 中调用：

```text
$ds-lite-iterate 只执行 action-contract-length.json 描述的一次 probe，验证结果，更新假设，给出责任汇报，然后停止。
```

手工复核 probe：

```bash
cd project
python materials/run_probe.py --output research/artifacts/probe-result-length.json
python <plugin>/scripts/ds_lite_state.py mission --root . --format json
```

不要执行 `hook-cases.json` 中的危险操作；只判断它们应当 `allow`、`block` 还是 `continue-once`。

## 预期产物

- 一个终态 `research/iterations/*.json` receipt。
- `probe-result-length.json` 保存 `a--b` 反例。
- `hypothesis_updates` 把原假设标成 `refuted`，不是 `supported`。
- `negative_results`、授权依据、未验证候选和 `user_report` 均非空。
- 最终反馈说明实际动作、验证、失败层、假设变化、下一动作与是否需要用户决定。

## 常见错误

- 看到前两个样例就提前写“已支持”。
- 把 probe 退出码 0 当成假设成立。
- 找到反例后删除原 idea 或负结果。
- finalize 之前开始第二个 probe。
- 只写总结，不登记 receipt、reflection 或 user report。
- 把 Hook 配置文件存在误写成宿主 Hook 已加载。

## 答案边界

本实验只证明 `a--b` 反驳当前长度保持假设，并演示一次协议闭环。它不验证数学、软件工程或数值仿真 profile，也不证明 fresh-host Hook 或隐式 skill 触发已工作。

## Windows 与 WSL

Windows 和 WSL 都可运行标准库 probe。WSL 路径使用 `/mnt/...` 或 ext4 工作区时，receipt 仍只写项目相对路径；不要把盘符根目录或 `/mnt/<drive>` 根写进协议文件。这个小实验不等同 Linux Codex 安装验收。

## OpenScience 主管示例

OpenScience 只下发一个 work unit 和一次 `collect-evidence` action。基层 worker 先登记 running receipt，回传反例和终态汇报；主管核验 receipt 后才决定是否批准下一轮更窄的假设测试。
