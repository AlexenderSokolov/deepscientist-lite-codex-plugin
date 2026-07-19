# DeepScientist Lite Codex Plugin

## 研究背景

本仓库实现一个面向教学、快速启动和小型科研项目的轻量 Codex 插件。它抽取 DeepScientist 工作流中可恢复、可审计、可教学的文件协议，不复制 daemon、Web/TUI、connector、MCP 或长期调度平台。

根目录 `PROJECT.md` 是本仓库的长期项目记忆；`plugins/deepscientist-lite/assets/templates/PROJECT.md` 是插件为用户项目生成的合同模板，两者职责不同。

## 基本假设

- 文件化项目合同、artifact 和显式状态图足以支持短周期科研工作的跨会话恢复。
- 状态内核应保持 Python 3.10+ 标准库实现，避免增加教学部署成本。
- Graph JSON 是机器权威状态，`RESEARCH_MAP.md` 是可重建的人类投影。
- 失败实验、旧路线和公开决策理由应保留，但不得记录隐藏思维链。

## 分析目标

- 可靠维护 intake、scout、idea、experiment、review、analysis/write 与单轮 iterate 的最小科研闭环。
- 将 AIResearch 暴露出的失败模式固化为协议规则：artifact 不是进度，ready 不是完成，idea 不是实验，metric 方向错误是协议失败，没有可见闭环就没有智能体体验。
- 防止并发覆盖、非原子写入、路径泄露和证据关系污染推进路线。
- 保持 Windows 与 Unix-like 环境中的命令、中文和空格路径可用。
- 为教学 Beta 提供可重复验证、证据审查、迁移和发布流程。
- 用领域中立 Factor Card 比较科研 idea 的新颖性、可行性、证据、成本、风险与任务对齐，同时抑制单一分数和自动真值错觉。
- 用统一沟通审计让 Agent 说明查阅、行动、验证、失败、限制、反思和交付依据，阻断没有项目内证据的完成声明。

## 工作流程

1. 通过七个 `ds-lite-*` skills 读取项目合同、状态和证据。
2. 先初始化 `ds-lite.communication-audit.v1`，写清开始前目标、事实、规则、复用资源、风险和停止条件；再写 artifact、memory 或可复现 `run_*.sh`。
3. Graph 写操作在锁内检查 revision、校验语义并原子替换。
4. 实验先生成 contract/Evidence Pack，再由独立 review 流程决定是否进入 analysis/write。
5. 每个有界任务由 `research/work-unit.json` 的 `ds-lite.work-unit.v1` 描述；claim-bearing evidence 只由 profile typed validator 升级，review 同时写 Markdown 和 `ds-lite.review-result.v1` sidecar。
6. idea 比较可写 `ds-lite.factor-card.v1` sidecar；六个分项独立保存证据与不确定性，no weighted total，且卡片只作为 decision artifact。
7. 每次 graph 提交后重建 `RESEARCH_MAP.md`；高频用户入口通过 `mission` / `render-status` 投影到 `STATUS.md`。
8. 使用统一验证脚本执行单元测试、仓库 smoke 和语法检查。
9. 用户文档按“README 快速上手—用户指南理解机制—实现文档维护细节”分层；教学课程用标准库 runner 准备确定性现场。

## 代码结构

- `plugins/deepscientist-lite/`：可安装插件、技能、模板、协议和状态脚本。
- `tests/`：Graph v2、CLI、迁移、并发和路径回归测试。
- `tools/validation/`：仓库级验证器与 shell/PowerShell 入口。
- `docs/`：设计、迁移、已知问题和发布维护资料。
- `plugins/deepscientist-lite/references/communication/`：运行时沟通核心、四个 profile、语言/学术叠加层和三阶段自审规则；`upstream/` 是不加载的完整审计快照。
- `plugins/deepscientist-lite/scripts/ds_lite_communication_audit.py` 与 `ds_lite_hook.py`：项目内审计收据和可选、确定性四事件 hook 适配器。
- `teaching/`：不进入运行时包的课程与演示材料。
- `teaching/lab_runner.py`：跨平台课程准备器；student 模式不预写审查结论，reference 模式只生成明确标记的教师答案。

## 运行流程

- Unix-like：`bash tools/validation/run_validate.sh`
- PowerShell：`powershell -ExecutionPolicy Bypass -File tools/validation/run_validate.ps1`
- 单元测试：`python -m unittest discover -s tests -v`
- 仓库 smoke：`python tools/validation/validate_repo.py`
- 教学课程：`python teaching/lab_runner.py --lab quickstart --mode student --output <path>`

## 验收标准

- Graph v2 写入具备跨平台锁、revision 检查和原子替换。
- v1 可读且可迁移，原 graph 备份永久保留；外部绝对路径不会被静默写入 v2。
- progression trace 不遍历 `supports`、`blocks` 或 `rollback`。
- 七个技能只通过 CLI 修改 graph，并能处理 revision 冲突；`ds-lite-iterate` 一次只推进一轮并停在 checkpoint。
- Evidence Pack 不保存凭据或本机绝对根目录，项目内证据可通过 SHA-256 复核。
- 新的 experiment→analysis 路线经过 review；旧 Graph v2 仍可读并仅产生兼容警告。
- 新项目无 claim requirement 时为 `planning`；普通 artifact/log/path 不升级证据。只有 profile typed validator 通过才能到 `has-evidence`，只有匹配的 typed review result 才能到 `reviewed`。
- Factor Card 正例、缺字段、错误 enum、路径逃逸、敏感字段、ID/因子冲突和 `extensions` forward compatibility 均有测试；卡片不能升级 evidence strength。
- Windows PowerShell、Git Bash、WSL DrvFS、WSL ext4，以及远程 Windows/Ubuntu CI 均通过统一验证入口。
- manifest、技能、模板、文档和发布版本保持一致。
- 六类教学实验可在 student/reference 模式运行；公开文档不把 Graph 说成推理链快照，不把 Evidence Pack 完整性说成科学真实性。
- `communication-audit.v1` 的 claims、protected content、八项 `honor-*` 检查和 handoff 可确定性校验；无证据的 `read/changed/verified/completed` 只能写成未验证/计划并由 Stop 阻断。
- hook 默认未启用，注册器必须先展示变更；宿主格式未经官方文档或真实主机验收确认时必须返回 `host_supported: false`，不得猜写 `.codex/config.toml`。
- 简单问答只满足适用的最小语义字段，不以固定字数强制冗长；高风险/`deep` 任务必须显式报告验证、限制、失败、反思和下一步。

## 设计决策

- 当前发布线：`0.5.0-beta.2`，Graph schema 继续为 `ds-lite.graph.v2`，Evidence schema 为 `ds-lite.evidence.v1`；Mission Board 和 `ds-lite.communication-audit.v1` 都是项目文件投影/收据，不是 Graph、Evidence 或 Work Unit 新字段。
- P0 引入独立 `ds-lite.work-unit.v1` 和 `ds-lite.review-result.v1` sidecar，不改变 Graph v2 或 Evidence Pack v1。`verdict` 表示 review gate，`claim_assessment` 表示 claim readiness；未知 schema 字段只允许放在 `extensions`。
- 通用 core 只面向科研与工程任务。`literature-evidence`、`mathematical-exploration`、`software-evaluation`、`numerical-simulation` 仅保留为 `reserved / not-validated`，不得据此宣称领域支持。
- `ds-lite.factor-card.v1` 固定六个科研/工程通用分项，不计算总分或自动赢家。Finance Factor 只保留为方法来源与 pressure-case fixture；WQ、Qlib、股票池和金融指标不进入 core、模板或默认 skill。
- 项目外资源使用 `external://alias/path`，绝对根目录由 `DS_LITE_EXTERNAL_<ALIAS>` 提供。
- 保留 `DeepScientist Lite` 名称，但明确声明为独立、非官方第三方插件。
- v0.2 不引入 MCP、daemon、Web/TUI、模型路由或长期 automation。
- `run_validate.sh` 必须兼容只有 `python3` 的 Unix/WSL 环境；运行时脚本保持 LF。
- CLI 文件内容固定使用 UTF-8；验证入口启用 Python UTF-8 模式，CLI 输出在旧 Windows 代码页下必须可安全转义，不能依赖宿主区域设置。
- 状态内核模块化属于 v0.2 之后的内部重构，必须保持 Graph v2 与 CLI 兼容。
- Review 是独立流程和 artifact，不宣称独立模型或物理隔离。
- v0.3 不加入 MCP、subagents、HPC/云调度或完整树搜索；评分循环只作为 Graph 分支教学。
- v0.4 不加入 daemon、MCP、Web/TUI 或长期后台调度；0.5.0-beta.2 只提供用户确认后才可注册的确定性 hook 适配器，插件 manifest 仍不声明 hooks，OpenScience 可作为上层主管调用 DS Lite worker。
- 外部长任务管护采用“稳定外部 owner 管进程，DS Lite 管文件化交接和证据”的责任模型。进程丢失的根因应先按生命周期归属错误排查；对话、Codex worker、tmux、实验进程和工件是五种独立状态。Lite 不拥有进程生命周期，只要求 Codex 登记、检查、备份、修复和恢复 `external-task-*` 记录，不能把临时 shell 内创建的 tmux 当作持久执行证明。
- tmux 容量申请必须先由 Codex 写成 `external-tmux-plan-*`，再由用户从独立稳定 shell 手动创建固定 socket、顶层 session 和计划内 pane；Codex 只验证、连接和使用已授权槽位。“子会话”不是 tmux 协议对象，用户这样表述时只解释为 pane-scoped Codex CLI child worker，其进程存活与 provider 对话可恢复性必须分别验证。
- 教学 runner 只负责确定性准备和协议故障，不冒充 Codex skill 或领域审查；课程默认保留所有输出，不覆盖已有目录。
- 教学 runner 完成场景准备后必须从最终 Graph 同步 `STATUS.md` 的 active node 与 revision，不能把初始化状态留给学生当作“故障”。
- 生成的 `run_*.sh` 不保存项目绝对根目录或 Codex cache 路径；本机运行时通过 `PYTHON_BIN`、`DS_LITE_EVIDENCE_CLI`、`DS_LITE_PLUGIN_ROOT` 等环境变量解析。
- 本地 marketplace 写入配置只代表来源已注册；安装须在 `/plugins` 等宿主提供的插件浏览界面中明确完成。缓存验收以新线程实际报告的版本、来源、UI 文案和七技能发现为准。
- Codex 验收工具只能创建新隔离目录并做只读宿主探测；`package_valid`、`host_supported`、`installation_verified` 和技能发现必须分别记录。
- 默认 `validate --strict` 继续审计全图；当前路线交接可使用 `--scope active-route`，但结构与路径完整性错误始终全局生效，非当前路线警告必须保留在输出中。
- 教学产物使用 `ds-lite.teaching-handoff.v1` 核对 Graph、STATUS、active route 与 revision；该投影不改变 Graph 作为机器权威来源的地位。
- `0.5.0-beta.2` 重新导入三个固定提交的完整快照，逐文件登记九字段采用矩阵，增加 `communication-audit.v1`、自审三阶段和可选 hook；fresh cache/new-thread、四 profile 的真实触发、hook 注册阻断和人工 A/B 仍是独立人工门，未验证前不得写成发布就绪。
- 2026-07-19 验收中，Windows、Git Bash 和 WSL 各通过 99 项单测、仓库 validator 与 `py_compile`；隔离 acceptance package 安装和七技能目录检查通过。真实 CLI canary 在 180 秒预算内无事件、最终反馈或 usage，已冻结为 `timeout/ambiguous`，因此真实 Agent 表达和 A/B 结论保持 `not-verified`。详见 `docs/maintainers/acceptance-beta2-20260719.zh.md`。
- 0.5 沟通层在独立 worktree 从干净基线重做；原工作区的 Factor Card、教学 pilot、`ds-lite-coordinate`、通用 `ds-lite` 和 iteration schema 不合并。只化用四事件 hook 边界及 reflection/user-report Stop 检查，路径级分类见 `docs/maintainers/preexisting-dirty-worktree-audit.zh.md`。

## 沟通与文风层

本版本的研究动机是：科研协作不仅要留下结果，还要让下一次会话看懂为什么这样做、检查了什么、哪里仍然不确定。运行时采用 `core`、`profile`、`fixture`、`reject` 四类边界：core 约束证据优先、过程透明和完成前验证；profile 控制表达方式；fixture 只用于固定回归和人工盲评；作者模仿、空泛哲思、强制冗长、修改数字/引用和外部 Agent 框架工作流明确拒绝。

项目根目录可选 `STYLE.md` 是表达合同，不是状态 schema。新项目由 `ds_lite_state.py init` 通过现有 `write_if_missing` 生成；已有文件保留字节不变；旧 Graph 缺失时只由 `$ds-lite-intake` 提示，用户同意后再创建。默认是 `research-peer + auto language + adaptive detail + auto academic`，用户可选择四个内置 profile 或编写原创 `custom` profile。

“八荣八耻”在本项目中按可执行的工程习惯解释：查档求证、对齐需求、请示规则、复用存量、完备测例、恪守架构、坦诚存疑、分步迭代。它不是要求每轮输出口号，也不覆盖证据纪律、执行权限或结构化内容保护。

验收包中的 12 个固定案例和匿名 A/B 评分表只属于人工验收资料，标记为 `runtime_loaded: false`，不得复制进 Evidence Pack 或运行时上下文。

`ds_lite_communication_audit.py` 的 `init`、`record-check`、`record-claim`、`finalize`、`validate`、`render` 只生成项目相对路径的审计收据。读取/修改声明绑定文件哈希，测试/验证/修复/完成声明绑定观测到的成功命令或验收结果；命令落盘前脱敏并保留脱敏文本哈希，审计 `finalize` 后封存为只读，最终完成态必须有受支持的完成声明。`Stop` 最多允许一次补救回合；`stop_hook_active` 不得把失败审计改成成功，第二次仍返回 `blocked`。简单问答不强制长篇，但适用的最小语义字段和不确定性仍不能省略。

## 已废弃方案

- Graph v1 的直接覆盖写入与无 revision 并发模型。
- 在 Python 中硬编码初始化文件，与 `assets/templates/` 形成双重来源。
- 使用所有边计算 Active Route。
- 在 graph 中保存项目外绝对路径。
