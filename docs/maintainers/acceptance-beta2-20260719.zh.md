# v0.5.0-beta.2 沟通增强版验收记录

本记录对应 communication worktree 的一次冻结验收。它只保存项目相对路径、版本身份、命令类别和结果分类，不保存完整对话、隐藏推理、原始 stderr、token、完整环境变量或工作站绝对根目录。

## 版本边界

- 分支：`codex/v0.5-communication-seven`
- 源码 HEAD：`992c53e9392623ce84da654b8d09d78bf444bce7`
- manifest 版本：`0.5.0-beta.2`
- acceptance package：`communication-beta2-20260719-02/`（外部 F 盘隔离目录）
- package manifest SHA-256：`CCD0AC68D81E038C0D88481358A4EBB9603747F251C3C32A3963CC89ABD3A7FC`
- acceptance record SHA-256：`B208FCC542B064C07195DAEE8C330B30E4C6C79B4776D35FBBC16E21C8BEB0E3`
- CLI：`codex-cli 0.144.5`
- 隔离安装版本：`0.5.0-beta.2+codex.codex-beta2-20260719`
- 隔离发现的七个 skill：`ds-lite-intake`、`ds-lite-scout`、`ds-lite-idea`、`ds-lite-experiment`、`ds-lite-review`、`ds-lite-analysis-write`、`ds-lite-iterate`

当前提交祖先已经包含一项早期 Factor Card 改动；本轮没有从另一个 factor workspace 合并新文件、九技能 gateway、delegation、pilot 或 iteration 草稿。

## 第一阶段：源码与确定性协议

| 编号 | 测试目的 | 输入与入口 | 执行命令 | 预期 | 实际观察 | 证据路径 | 结论 | 未验证项 | 下一动作 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| C1 | audit 初始化、相对路径和哈希边界 | communication audit fixture | `python -m unittest tests.test_communication_audit` | 路径逃逸、绝对路径和错误目录拒绝 | 相关单测通过；相对路径哈希绑定生效 | `tests/test_communication_audit.py` | 通过 | 未在宿主 Hook 中观察 | 保留源码门 |
| C2 | 完成性声明必须绑定事实 | audit claim/check API | 同上及统一入口 | `read/changed/tested/verified/fixed/completed` 无证据不能通过 | 未观测命令、伪造 exit code、文件存在冒充完成均被拒绝 | `tests/test_communication_audit.py` | 通过 | 模型是否遵守未测 | 进入真实 canary |
| C3 | 缺命令、未运行命令和伪造结果 | command evidence fixtures | `powershell ... run_validate.ps1` | 无实际命令结果不能 finalize | 99 项测试和 validator 均有真实退出码；伪造 fixture 被拒绝 | `acceptance-audit.json`、`tests/test_communication_audit.py` | 通过 | 不证明 Agent 会报告它 | 记录未验证 |
| C4 | 失败、阻塞和 ambiguous 保留 | failed/blocked audit cases | 统一入口 | 负结果不能改写成成功 | failed audit、缺 handoff、unsupported completion 均阻断 | `tests/test_communication_hook.py` | 通过 | 无真实 Agent 失败流 | 真实调用需 canary 通过 |
| C5 | protected content 不被润色层改写 | 数字、命令、路径、JSON、引用 fixture | `python -m unittest tests.test_communication_audit` | 结构化和学术事实保持原字节 | protected hash 变更被阻断；命令敏感值脱敏 | `tests/test_communication_audit.py` | 通过 | 未做模型文本盲评 | A/B 延后 |
| C6 | profile/detail 只改变表达密度 | 四 profile 与 `concise/adaptive/deep` | `python -m unittest tests.test_communication_layer` | 不改变证据义务和权限 | 四 profile、引用渐进加载和 style 合同通过 | `tests/test_communication_layer.py` | 通过 | fresh thread profile 触发未验证 | 保持 `not-verified` |
| C7 | Hook 确定性安全边界 | PreToolUse/PostToolUse/Stop adapter | `python -m unittest tests.test_communication_hook` | graph 直写、递归删除、破坏性 git、提权和无证据完成阻断 | 相关行为均通过；不保存原始命令文本 | `tests/test_communication_hook.py` | 通过 | 宿主是否自动加载 Hook 未验证 | 不改 manifest |
| C8 | Hook installer fail closed | 未知宿主 | `ds_lite_hook.py install --show/--apply` 的单测 | `host_supported=false` 且不写 config | 单测确认不覆盖既有配置、不写 `.codex/config.toml` | `tests/test_communication_hook.py` | 通过 | 真实宿主注册未验证 | 等待独立授权门 |
| C9 | Graph v2、Evidence v1、旧 CLI 兼容 | 原有 state/evidence fixtures | `powershell ... run_validate.ps1`、Git Bash、WSL | 旧协议不回归 | Windows、Git Bash、WSL 均 99/99；validator、`py_compile` 通过 | `tools/validation/run_validate.ps1`、`run_validate.sh` | 通过 | macOS 未验证 | 发布说明分层 |

源码验证统计：Windows PowerShell 99/99；Git Bash 99/99；WSL `DS-Lite-Ubuntu-24.04` 99/99。三处仓库 validator 均通过，`py_compile` 均通过。WSL 仅有宿主 PATH 的 `E:\PyCharm 2025.2\bin` 转换警告，不是仓库测试失败。

## 第二阶段：隔离 package 与真实 Agent canary

| 测试编号 | 测试目的 | 输入与 skill | 执行命令 | 预期 | 实际观察 | 证据路径 | 结论 | 未验证项 | 下一动作 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| P1 | acceptance package 完整性 | 冻结源码快照、12 个 communication fixture | `prepare_codex_acceptance.py`、`audit_codex_acceptance.py --require-host` | package 有效、版本一致、七技能清单完整 | `package_valid=true`、`host_supported=true`、无 errors | `acceptance.json`、`acceptance-audit.json` | 通过 | fresh thread 尚未观察 | 保留包 |
| P2 | 隔离 marketplace 与安装 | F 盘隔离 `CODEX_HOME` | `codex plugin marketplace add`；`codex plugin add deepscientist-lite@...` | 只写隔离 home，发现准确版本 | 注册成功；安装成功；七个 skill 目录可见；正式 cache 未改 | 外部隔离 home 的 `config.toml` 与安装目录 | 通过 | 新线程实际 skill 触发未验证 | 不覆盖正式 cache |
| P3 | fresh Agent communication canary | 只读工作树，隐式项目识别请求 | `codex exec --ephemeral --json --model gpt-5.6-sol --sandbox read-only`，上限 180 秒 | 有事件、最终反馈和 usage | 首次参数调用被 CLI 拒绝（不支持 `--ask-for-approval`）；改用支持参数后运行 214 秒仍无任何输出，命令超时 `124` | 本报告；未产生原始 JSONL | `timeout/ambiguous`，冻结 | 无法验证插件是否被 Agent 采用、目标/事实/授权/停止条件表达、receipt 和用户报告 | 不启动七个 fresh-agent 或 A/B |

P3 的两次参数失败/超时不会被归因于插件功能，也没有自动重试。按照规则，canary 未出现 `turn.completed`、最终反馈或有效 usage，因此七个 skill 测试和四组 A/B 对照均保持 `not-verified`。

## 第三阶段：真实表达与 A/B

七个 fresh-agent 测试（intake、scout、idea、experiment、review、analysis-write、iterate）未启动。四条 matched route（intake→scout、idea→review、experiment→analysis、iterate→handoff）未启动。没有三组有效 matched pair，不能声称“表达改善”，也不能把源码测试当成用户体验证据。

## 发布判断

本版本可以作为 source/package prerelease 发布，发布说明必须明确：源码与隔离安装已验证；fresh thread、真实 Agent 表达、宿主 Hook 自动加载、正式 cache 更新和人工 A/B 尚未验证。发布不应写成稳定版，也不应宣称插件已经改善 Agent 的实际沟通行为。

外部遗留事项：误用 PowerShell 自动变量曾在 `C:\Users\20600\config.toml` 产生一个 0 字节文件，marketplace 条目已撤销，默认 `.codex\config.toml` 未留下该条目。该空文件需要用户明确同意后才能删除；在获得同意前不再写默认配置。
