# DeepScientist Lite 教学课程

这里不是功能清单，而是一条可以照着走的学习路线。课程面向第一次接触科研工作流插件的学生：先看见一个项目怎样留下状态，再学习如何检查证据、比较分支和处理冲突。

插件本体位于 `plugins/deepscientist-lite/`。本目录只放课程、确定性 fixture 和教学 runner，不会进入插件运行时。

## 从哪一课开始

| 课程 | 时间 | 适合谁 | 学完应能回答 |
| --- | ---: | --- | --- |
| [快速体验](quickstart-20.zh.md) | 20分钟 | 所有人 | PROJECT、STATUS、Graph 和 artifact 各自做什么？ |
| [证据审查](evidence-lab-45.zh.md) | 45分钟 | 做过一次实验的人 | 运行成功、证据完整、指标达标和结论可用有什么区别？ |
| [三分支决策](scored-branch-lab-90.zh.md) | 90分钟 | 研究生课程、组会工作坊 | 为什么最高分路线也可能必须被阻塞？ |
| [路线语义](route-lab-30.zh.md) | 30分钟 | 想理解 Graph 的人 | `supports` 和 `rollback` 为什么不改变 Active Route？ |
| [路径可移植](path-lab-30.zh.md) | 30分钟 | 跨 Windows/WSL 协作的人 | 项目外数据怎样关联而不泄露绝对根目录？ |
| [Revision 冲突](revision-lab-30.zh.md) | 30分钟 | 多会话协作或系统课程 | 陈旧写入为什么被拒绝，怎样安全重试？ |
| [Matched Control Pilot](matched-control-pilot.zh.md) | 多轮 pilot | 课程设计者、插件维护者 | 文件化任务协议是否改善恢复、证据和负结果管理？ |

第一次使用建议按“20分钟快速体验 → 45分钟证据审查 → 90分钟分支决策”完成。后三门是协议专题，可以按需要选择。

## 两种上课方式

### 引导模式：脚本准备，学生或 Codex 作判断

教学 runner 只创建可重复的数据、Graph 状态和故障现场。学生读取文件，调用 `$ds-lite-*` 技能，再提交自己的 review 或路线决定。

### 一段式挑战：让 Codex 完成整条路线

每门课都提供一段可复制提示词。学生把任务交给 Codex，再用 `lab-result.json`、Graph 和评分表检查 Codex 是否绕过契约、审查或冲突恢复。

这种模式更接近真实使用，但结果会受模型和上下文影响，因此不能替代确定性脚本检查。

## 运行课程

Python 入口在 Windows、Git Bash 和 WSL 中一致：

```bash
python teaching/lab_runner.py \
  --lab evidence \
  --mode student \
  --case clean \
  --output .validation-tmp/my-evidence-lab
```

Git Bash / WSL：

```bash
bash teaching/run_lab.sh --lab evidence --mode student --case tampered
```

PowerShell：

```powershell
powershell -ExecutionPolicy Bypass -File teaching/run_lab.ps1 `
  -Lab evidence -Mode student -Case threshold-miss `
  -Output .validation-tmp\my-threshold-lab
```

`--lab` 可选 `quickstart`、`evidence`、`branches`、`route`、`paths`、`revision`、`matched-pilot`。只有 evidence 使用 `--case clean|tampered|threshold-miss`；matched pilot 只接受 student 模式，教师材料会另行生成。

准备四案例、三 arm 的对照包：

```bash
python teaching/lab_runner.py \
  --lab matched-pilot \
  --mode student \
  --output .validation-tmp/matched-pilot-01
```

该命令只生成 12 个隔离工作区、分轮提示、空白评分面和学生/教师指南，不会调用 Codex 或预填比较结果。真实运行前必须固定模型、预算、工具和材料，并取得明确授权。

## 输出里有什么

每次运行创建一个新工作区，已有目录会被拒绝，不覆盖、不自动删除：

```text
<workspace>/
  LAB_README.md          # 本次实验下一步
  COMMANDS.md            # 准备阶段真实调用的命令，路径已脱敏
  lab-result.json        # 机器可检查的现象
  logs/                  # 拒绝写入或校验失败日志
  project/               # 可以交给 Codex 的 DS Lite 项目
  REFERENCE_ANSWER.md    # 仅 reference 模式生成
```

student 模式不会预写 review 或 analysis。reference 模式才生成带“教师参考”标记的答案，避免把复制好的结论伪装成技能运行结果。

## 教师和学生材料

- [课程组织建议](lesson-plan.zh.md)
- [现场演示脚本](demo-script.zh.md)
- [教师指南](instructor-guide.zh.md)
- [学生工作表](student-worksheet.zh.md)
- [评分表](instructor-rubric.zh.md)
- [参考答案](answer-key.zh.md)

教学 fixture 只能说明协议如何工作，不能证明某个科研方法有效，也不能作为插件稳定版发布的唯一证据。
