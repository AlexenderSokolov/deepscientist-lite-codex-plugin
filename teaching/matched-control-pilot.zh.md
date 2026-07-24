# Matched Control Pilot：比较普通 Codex、单文件记忆与 DS Lite

这套 pilot 用四个小型科研/工程任务比较三种工作方式。它研究的不是“哪次回答看起来更聪明”，而是任务在需求变化、上下文重启、负结果和证据审查下能否保持连续、可核验、少返工。

课程 runner 可以准备材料、执行清单和评分协议；真实 Codex 调用、子智能体 forward test 和成本消耗必须另行取得用户明确授权。未执行时，所有结果都保持 `prepared-not-run` / `pending`。

2026-07-17 的首个授权 pilot `matched-pilot-20260717-01` 已按固定顺序启动，但在第一个 plain 工程调用中以 `process-failed` 停止，完成数为 `0/18`。执行器没有启动后续 arm，也没有自动重试。该运行只能作为 fail-closed 教学失败案例，不能用于 arm 效果比较；详见[失败案例记录](pilot-failure-case-20260717.zh.md)。

2026-07-18 的第二次验收使用九技能隔离 home。preflight 通过，但唯一隐式 canary 建立 thread 后以 `rate-limit` 类别、0 token/tool、无 terminal turn/反馈和 `timeout` 结束；因此没有启动 trigger 或任何 arm。该案例同时暴露并修复了 Windows `.cmd` 子进程树超时收束问题，但该缺陷不能解释 provider failure。详见[canary 失败案例](canary-failure-case-20260718.zh.md)。

## 一、实验问题

三个 arm 使用相同任务、材料、提示顺序、模型、预算和工具：

| arm | 允许的连续性机制 | 禁止项 |
| --- | --- | --- |
| plain | 请求中指定的代码、测试和最终报告 | DS Lite、持久 scratchpad、读取其他 arm |
| scratchpad | plain 的产物，加一个 `NOTES.md` | DS Lite、第二份协调笔记、读取其他 arm |
| ds-lite | PROJECT、STATUS、Graph、work unit 和显式 artifacts | 直接编辑 Graph、子智能体委派、后台循环 |

只有记忆/执行协议不同。若某个 arm 得到额外答案、更多预算或不同工具，本次比较作废，不能靠事后解释修补。

## 二、四个案例

### A. 工程连续性

一个小型 Python slug 工具依次经历：

1. 修复当前失败测试；
2. 增加 Unicode 归一化和空结果错误；
3. 更换上下文后，从文件恢复状态，再增加保留字规则。

第三轮计时从重启提示出现开始。评分同时看最终测试、旧需求保持、恢复说明、重复工作和状态遗漏。不能把“重新跑一遍测试”计为返工；只有已经有完成证据却被无意义重复的动作才计入。

### B. 数学反例

材料给出 `n=0..39` 时 `n^2+n+41` 都是素数的观察。任务要求审查“对所有非负整数都为素数”的全称命题，并用标准库脚本继续搜索。

关键教学点：大量支持样例不是证明；一个合法反例足以否定全称命题；发现负结果后必须保留机器输出和论证边界，而不是把失败改写成“总体趋势仍好”。

### C. 多 seed 数值研究

材料中的模拟先运行 2 个 seed，再扩展到至少 20 个 seed。极小 seed 子集会给出容易误导的排序，但扩展结果仍需按不确定性解释，不能追加未经预注册的显著性宣称。

这个案例在 Windows 和 WSL 都只依赖 Python 标准库。单次教学运行验证的是工作流行为，不会把 `numerical-simulation` profile 升级为已验证支持。

### D. 科研创新评价

固定来源包提供三个候选 idea。参与者按 `novelty / feasibility / evidence_strength / cost / risk / alignment` 六项比较，并给出不确定性和最小验证实验。

novelty 没有来源时必须保持未知；cost/risk 表示负担，不能作为正向加分项混进自动总分；评价卡不是实验 evidence，也不能把 claim 自动升级为 supportable。金融材料只提供方法启发，不进入本课程默认字段。

## 三、准备工作区

PowerShell：

```powershell
python teaching\lab_runner.py --lab matched-pilot --mode student `
  --output .validation-tmp\matched-pilot-01
```

Git Bash / WSL：

```bash
python3 teaching/lab_runner.py \
  --lab matched-pilot \
  --mode student \
  --output .validation-tmp/matched-pilot-01
```

已有输出目录会被拒绝。runner 不覆盖、不合并、不自动清理先前产物。

生成结构：

```text
<pilot>/
  PILOT_README.md
  STUDENT_GUIDE.zh.md
  INSTRUCTOR_GUIDE.zh.md
  RUBRIC.csv
  pilot-manifest.json
  prompts/engineering-continuity/
  arms/<case>/<plain|scratchpad|ds-lite>/
  results/README.md
  results/scores.csv
```

`pilot-manifest.json` 为每个 run 保存唯一 id、相对 workspace、提示引用、输入 SHA-256 摘要和待写结果引用。它是教学执行清单，不是插件运行时 schema。

获得真实执行授权后，维护者使用统一入口分阶段运行：

```powershell
$windowsRoot = '<FRESH_WINDOWS_PILOT_ROOT>'
$wslRoot = '<FRESH_WSL_PILOT_ROOT>'
$codex = '<CODEX_0_144_5>'
powershell -ExecutionPolicy Bypass -File teaching/run_pilot.ps1 -Action prepare `
  -WindowsRoot $windowsRoot -WslRoot $wslRoot -PilotId <FRESH_PILOT_ID> `
  -AuthorizationRef <AUTHORIZATION_REF>
powershell -ExecutionPolicy Bypass -File teaching/run_pilot.ps1 -Action install `
  -WindowsRoot $windowsRoot
powershell -ExecutionPolicy Bypass -File teaching/run_pilot.ps1 -Action preflight `
  -WindowsRoot $windowsRoot -WslRoot $wslRoot -CodexBin $codex
powershell -ExecutionPolicy Bypass -File teaching/run_pilot.ps1 -Action canary `
  -WindowsRoot $windowsRoot -CodexBin $codex -TimeoutSeconds 180
```

Bash 入口使用同样的 `prepare|install|preflight|canary|run|resume|score` action，并从 `PILOT_WINDOWS_ROOT`、`PILOT_WSL_ROOT`、`PILOT_ID`、`PILOT_AUTHORIZATION_REF` 和 `CODEX_BIN` 读取显式参数。`install` 只是隔离 skill home，不是 cache 安装。preflight 不调用模型；canary receipt 已存在时拒绝重试。只有 canary 通过并取得新的阶段授权后才能执行 `run`。`resume` 只跳过已确认 completed 的调用；发现 running、failed、timeout、ambiguous 或 duplicate risk 时会拒绝继续。它不是“从失败处再试一次”的快捷方式。

## 四、执行前预注册

教师或实验操作者必须先填定：

- 准确模型名称和版本；
- 每轮共同提示预算与停止条件；
- 允许的工具、联网策略和超时；
- arm 顺序或随机化方法；
- 成本单位与计时方法；
- 脱敏产物保存范围；
- 中断、部分完成和工具不可用时的记分规则。

manifest 中仍有 `pending-operator-input` 时不得开始横向比较。不同 provider 的成本单位不能直接混算。

## 五、隔离执行

1. 每次用宿主 sandbox，或把一个 `arms/<case>/<arm>/` 复制到独立执行根，只向任务暴露该 arm。
2. 不把 pilot 根目录作为模型工作区。仅用 `cd` / `Set-Location` 切换当前目录不是访问控制，无法保证模型读不到教师材料和兄弟 arm。
3. 先投递 arm 内 `TASK.md`。工程案例完成一轮就停止，由操作者再投递下一轮提示。
4. 第二轮工程任务完成后新建上下文；第三轮不得附带先前聊天摘要，只能依赖 arm 文件恢复。
5. 数值案例真实执行脚本并保留逐 seed JSON。WSL 示例：

```bash
cd arms/numerical-seeds/plain
python3 materials/run_simulation.py --seed-count 2 --output early.json
python3 materials/run_simulation.py --seed-count 20 --output expanded.json
```

6. 每个 run 结束后保存请求的文件、验证命令/退出码、耗时和统一成本。不要保存完整对话、隐藏推理、凭据、完整环境变量或工作站绝对根目录。

## 六、统一评分

`RUBRIC.csv` 定义以下指标：

- `task_correctness`：测试或证据检查是否支持任务结论；
- `recovery_time_seconds`：重启后恢复到有文件依据状态所需时间；
- `repeated_work_count`：已有完成证据却被无意义重复的动作数；
- `state_omission_count`：交接时遗漏的必需事实数；
- `negative_result_retained`：反例、排序反转和失败尝试是否保留；
- `evidence_traceability`：结论能否追到命令、输出、来源或 typed ref；
- `route_recovery`：能否恢复当前位置、下一步和回滚条件；
- `artifact_fragmentation`：未被权威入口引用的交付碎片比例；
- `speculation_leakage`：无支持却写成既定事实的主张数；
- `cost_units` 与 `information_gain_per_cost`：统一成本面上的信息产出。

碎片率不是简单文件数。DS Lite 本来就会生成多个职责分离的文件；只要 PROJECT/STATUS/Graph 能把它们组织成可恢复入口，就不应按“文件多”扣分。

建议先隐藏 arm 标签再评分。教师应记录可复查依据，而不是只给印象分。

## 七、答案边界

- 工程案例有可运行测试，但测试通过不自动证明交接质量好。
- 数学案例有可计算的决定性事实，教师不得提前写进 arm。
- 数值案例有确定性 seed 序列，但排序变化不等于统计显著。
- 创新评价没有预设唯一赢家；来源约束、未知项和最小实验比整齐排名更重要。
- Factor Card、PROJECT、STATUS、普通日志和任意非空路径都不是 claim-bearing evidence。

## 八、结果解读

首批 12-arm pilot 只报告描述性结果，不作统计显著性宣称，也不把一次模型表现外推到所有科研、工程或办公任务。文献、数学、软件和仿真 profile 继续是 `reserved / not-validated`；教学案例只验证 fail-closed 边界和工作流现象。

若某个 arm 中断，记录 partial/blocked 和实际产物，不补跑成“完整结果”；若 transport 状态不明且存在重复风险，不自动重试。任何真实子智能体委派仍需单独授权，不能由本课程 runner 自动发起。

## 九、常见错误

- 把 pilot 根目录交给模型，导致读到教师材料；
- plain arm 私自建立长期 scratchpad；
- scratchpad arm 建立多份散落笔记；
- DS Lite arm 直接编辑 `graph.json` 或把 Factor Card 当 evidence；
- 工程三轮一次性投递，消除上下文重启变量；
- 只保存最终文字，不保存命令、测试或反例；
- 因 12 个结果看起来整齐就宣称统计优势；
- 用一次教学案例宣称保留 profile 已获得领域支持。
