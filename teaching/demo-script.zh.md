# 20分钟现场演示脚本

## 演示前准备

确认新线程能发现 `$ds-lite-*` 技能。另开终端，准备运行教学 runner。不要使用已经写好 review 的 reference 模式。

## 0–3分钟：抛出问题

对听众说：“假设我们现在换一个 Codex 会话，只保留项目目录，新会话怎样知道做到了哪里？”先收集回答，再说明今天不比较模型能力，只看项目能否交接。

## 3–6分钟：准备工作区

```bash
python teaching/lab_runner.py --lab quickstart --mode student --output .validation-tmp/demo-quickstart
```

打开 `LAB_README.md`，说明 runner 只准备状态，不调用技能替人作答。

## 6–12分钟：看四处文件

依次打开：

1. `project/PROJECT.md`：圈出目标和验收标准；
2. `project/STATUS.md`：圈出当前节点和下一步；
3. `project/RESEARCH_MAP.md`：沿 Active Route 走一遍；
4. `project/research/artifacts/`：打开 scout 和 idea 记录。

每打开一个文件，只问“它回答什么问题”，暂时不讲 JSON 字段。

## 12–16分钟：让 Codex 接手

在 `project/` 中发送：

```text
$ds-lite-intake 这是一个已有 DS Lite 项目。请只读取当前项目状态，不覆盖文件；告诉我项目目标、当前节点、已有证据和下一条可执行动作。如果发现模板内容或证据缺口，请明确指出。
```

对照 Codex 回答与文件。若回答超出文件证据，现场指出“恢复上下文不等于允许补写事实”。

## 16–20分钟：展示边界

说明三件事：Graph 保存公开状态，不保存隐藏思维链；生成模板不等于 intake 已完成；插件不会证明科研结论为真。

结束问题：“如果实验分数很好，但输出文件后来被改过，下一步该看什么？”由此进入45分钟证据审查课。
