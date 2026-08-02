# 上游设计原子吸收审计表

本文是 0.8 验收轮的可核对清单。它审计的是“设计原子是否被重新设计为 DS Lite 协议、实现和测试”，不是仓库是否被整仓复制。所有采用均以 `evaluation/cross-disciplinary-upstreams.json` 中的固定 commit、许可证和哈希为身份；未观察到的宿主行为不会由离线测试推断。

| 上游 | 精华设计原子 | DS Lite 的实质落点 | 验收/证据 | 吸收深度 | 明确排除 |
|---|---|---|---|---|---|
| ARS-Codex | 动机、方法、证据、局限、贡献五层收敛；claim 定位；阅读范围；多索引冲突解释；引用失败修复建议 | Academic `citation-check.v1`、batch envelope、`metadata-only/abstract/full-text` 阅读范围、claim 页码/章节定位；Core 0.8 后再启用可选 Socratic intake | `tests/test_academic_protocols.py`；Academic live-provider 仍待真实宿主 | clean-room profile，已协议化 | CC BY-NC 提示词、Material Passport 状态机、Hook/agent-team runtime |
| Claude Scholar | Sources→Knowledge 晋升；Zotero/DOI/arXiv 导入边界；重复、更新、分层知识 | Knowledge `pull-scholaraio`/proposal；只写来源引用和 pending proposal；ResearchKB accepted 必须带原生 review ref | `tests/test_extension_protocols.py`；真实 ScholarAIO CLI/API 尚未观察 | companion adapter，边界已实现 | 第二套 Obsidian KB、论文解析器、默认 Hook、重复 planning 状态机 |
| Tapestry | capture/feed/note 分层；中文平台连接器；撤回和更新意识 | Knowledge `pull-tapestry`；来源 URI、抓取时间、内容哈希、撤回/supersede proposal；数据留在外部 root | Knowledge adapter 协议测试；真实 Tapestry doctor/export 仍待外部实例 | alpha adapter，协议已实现 | 将数据写入插件缓存 `_data/`、整体 vendor、正式知识自动升级 |
| awesome-ai-research-writing | 写作任务索引、遗漏能力清单、回归案例来源 | 转成 Academic/Core 写作需求覆盖矩阵；约束“事实保持、负面结果、限制说明、术语一致性、AI 套话密度” | communication audit 与文字回归测试 | fixture/index，未复制提示词合集 | 整仓提示词镜像、近义 skill 入口 |
| Rebuttal-Skill | concern 原子化；可行性判断；P0-P3 实验优先级；结果回填；负面结果；resubmission gate | `nature-response` revision guard、adversarial reviewer/fresh adjudicator、resubmission gate；每轮有界 checkpoint | Academic 回归计划；真实宿主隔离仍待观察 | clean-room profile，已融入既有入口 | 未授权原文复制、无人审稿循环、独立 rebuttal 状态机 |
| nature-skills | 论文结构、Nature 风格、response/reviewer、图表与数据约束 | Academic 17 skill 保持原入口；修复 Core 写作路由，按能力发现 `$nature-polishing/$nature-writing/$nature-response` | 包矩阵、文字层回归；Fresh Desktop 未通过前不宣称加载 | existing profile，跨包联动已实现 | Academic 接管 Core 状态、重复 evidence/iteration 状态机 |
| codex-autoresearch | 目标冻结、完成信号、恢复、失败冻结、零隐式重试 | Core `ds-lite-iterate`、external task record、停止门、失败 attempt 保留；长任务由外部 owner 持有 | offline loop receipt；真实长任务 owner/reconnect 待用户 bootstrap | core behavior，协议已落地 | 无限循环、daemon、自动 tmux、自动 retry |
| AI-Research-SKILLs | 微调、RAG、评估的参数与质控需求 | 记录为第二批 AI 包需求矩阵和 fixture 设计，不进入 0.8 运行时 | `evaluation/cross-disciplinary-upstreams.json`；未发布 AI 包 | deferred profile | 90+ skill catalog、整仓镜像、专业依赖自动安装 |
| Auto Empirical | estimand、识别、样本/变量、诊断、稳健性、缺失、负面结果、Golden Workflow | Empirical 单入口与 `empirical-spec/result.v1`；最终结果引用 Core Evidence Pack；不把显著性当结论 | `tests/test_empirical_pack.py`、Empirical validator | fixture + clean-room profile，Alpha 包已实现 | CC BY-SA 聚合 catalog、嵌套 skill runtime、第二套数据仓库 |
| Scientific Agent Skills | RDKit、Scanpy 等专业工具适配；环境 doctor；专业失败诊断 | 保留 RDKit/Scanpy adapter candidate 接口和 doctor 要求 | 第二批 fixture 设计；本轮未安装专业 runtime | deferred adapter | 148 skill 全量引入、自动部署专业库 |
| codex-claude-academic-skills | FFT、窗函数、频率分辨率、缩放、采样率、混叠、泄漏、单位、随机种子、图轴 | Engineering `engineering-analysis.v1` 与单入口；NumPy/SciPy 基准；MATLAB/Octave 能力发现 | `tests/test_engineering_pack.py`、Engineering validator | clean-room profile，Alpha 包已实现 | Office 入口、重复论文写作入口、伪造参数/结果 |
| ARIS | fresh-context reviewer；单一最强反对意见；编辑白名单；claim/citation audit；有界多轮 | `nature-reviewer` adversarial mode、revision constraints、每轮停在 checkpoint | Academic 回归计划；真实 fresh reviewer 隔离仍待宿主 | clean-room profile，已融入既有入口 | 无人值守循环、monitor、MCP、实验队列、自动造数据 |
| Kim_Service | 核心问题门；需求消歧；触发评测；baseline；来源抽象；真实验收证据；工业代码质量控制 | `quality-plan/result.v1`、communication audit、用户动作请求/响应、Hook/Stop 门、包矩阵和 release gate | `tests/test_quality_protocol.py`、`tests/test_communication_hook.py`、本轮用户动作测试 | maintenance/evaluation layer，已实质吸收 | Memory/Goal/Decision/Teams 第二套状态机 |
| Superpowers | brainstorming、TDD、debugging、verification 的按需协作 | 仅做能力发现和 workflow smoke；Superpowers 拥有通用开发流程，DS Lite 拥有科研状态、证据、批准、停止规则 | `audit_superpowers.py` 与兼容性测试 | selective adaptation | vendor、第二套状态机、复制 TDD/debug skill |
| Playwright / Firecrawl / agent-browser | 公开网页交互、正文抽取、后端 challenger、预算和失败诊断 | Web `capability.v1`、`source-record.v2`、public-only、domain/页数/字节/时间预算；stdlib HTTP 已真实执行，宿主浏览器已覆盖静态/JS/PDF | G 盘 `web-real-20260726` source-record；Playwright/agent-browser/Firecrawl 当前 `not-observed` | layered backend，已协议化；真实 CLI 部分待授权 | browser-use 默认 Agent 循环、PinchTab/集群控制面、登录态和表单提交 |

## 当前结论

本表中“已实现”只表示原子已经进入独立协议、代码落点和测试；不表示真实 provider、Hook、Desktop 或 OpenScience 已通过。当前仍有硬门：pinned Codex/trusted Hook、真实 child delegation、长任务 owner/reconnect、matched effect、formal cache、fresh Desktop、OpenScience fresh task 和 release gate。

## 证据位置

- 机器审计：`evaluation/cross-disciplinary-upstreams.json`
- 包矩阵：`tools/validation/validate_packages.py`
- 学习与质量：`docs/maintainers/learning-quality-protocol.zh.md`
- 用户动作协议：`plugins/deepscientist-lite-core/scripts/ds_lite_user_action.py`
- 本轮 Web 真实证据：用户授权临时根 `G:\DS-Lite-validation\web-real-20260726`
- 本轮 trusted Hook blocker：`G:\DS-Lite-validation\user-action-request-trusted-hook-20260726-01.json`
