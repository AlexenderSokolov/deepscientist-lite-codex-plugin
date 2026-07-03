# DeepScientist Lite 教学区

这里放的是讲解和演示材料。插件本体在 `plugins/deepscientist-lite/`，教学区不会参与插件运行时加载。

## 适合怎么用

- 组会里用 20-30 分钟讲清 DeepScientist Lite 的设计思路。
- 用 45 分钟实验讲清契约、Evidence Pack、篡改检测与审查门。
- 用 90 分钟实验讲清评分分支、违规高分和路线决策。
- 给新同学演示一个可回溯科研工作流应该长什么样。
- 用教学案例说明：旧项目接入、idea 分支、实验记录、负结果保留、下一步路线。

## 文件

- `lesson-plan.zh.md`：讲解提纲，适合老师、师兄或助教备课。
- `demo-script.zh.md`：现场演示脚本，适合照着操作一遍。
- `cases/paradigm-comparison-case.md`：教学案例，用来说明插件如何保留研究路线。
- `evidence-lab-45.zh.md`：证据链与篡改诊断实验。
- `scored-branch-lab-90.zh.md`：三分支评分与审查实验。
- `student-worksheet.zh.md`、`instructor-rubric.zh.md`、`answer-key.zh.md`：课堂材料。
- `run_evidence_lab.sh`：生成并保留一个完整 experiment→review→analysis 演示项目。

## 提醒

教学案例只是帮助理解插件，不是插件本身，也不是插件发布质量的判据。判断插件是否可用，主要看安装、skill 触发、文件协议、状态图和回溯是否稳定。

