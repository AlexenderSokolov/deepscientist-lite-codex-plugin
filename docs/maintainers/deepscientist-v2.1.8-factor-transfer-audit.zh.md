# DeepScientist V2 v2.1.8 Financial Factor 迁移审计

## 结论

本审计把 DeepScientist V2 v2.1.8 的 Financial Factor Mode 当作压力案例，不把金融任务模型搬进 Lite core。Lite 只独立实现能在科研与工程任务中确定性验证的不变量，并继续复用 work unit、Graph v2、Factor Card、typed evidence/review 和 STATUS；不新增 factor-portfolio schema。

权威上游与对象身份：

- release：<https://github.com/WENGSYX/DeepScientist_V2/releases/tag/v2.1.8>
- annotated tag：`9dacda3c67cab4bcabe30cd9029b51e16e3e6c22`
- tag commit：`49ffdcda6ce159505f6119b1e26d79c8503a8286`
- `resources/skills/wq-alpha-research/SKILL.md` blob：`6f58083e8f0a951a0773d94f5b0812484febc8c3`
- linked integration reference blob：`fc48d2b7ef6db95be30e44e425cdf2e9be598aa5`
- Financial Factor model source blob：`53728115fed331e3ea5bf3b67c79b18215f3b4ff`
- repository license：`AGPL-3.0-only`，见上游 `LICENSE`、`NOTICE` 与 `package.json`

## Case-to-Core 映射

| upstream fact | 通用不变量 | Finance residue | Lite 映射 | classification |
| --- | --- | --- | --- | --- |
| skill 及 linked reference 要求未测量指标省略，不以 0 或估算代替 | 未测量值保持 unknown；缺测与测得的零不同 | Sharpe、Fitness、turnover 等指标 | Factor Card `score=null/confidence=unknown`；typed evidence 决定 claim readiness | core |
| candidate 必须保留机制假设、选择理由、当前判断、真实 checks、证据和 decision reason | 状态提升必须能回溯到真实检查、证据引用和明确决定理由 | 因子表达式、WQ 检查名、相关阈值 | idea artifact、Factor Card、Evidence Pack、typed review | core |
| external submit 被接受后仍需重新查询，只有实际状态复核后才可记录 active | 外部 pending/submit 与 verified 是不同状态 | WQ submit、ACTIVE、SELF_CORRELATION | 通用 review/receipt 只接受适用 validator 的复核结果；外部 pending 不升级 | core |
| linked reference 规定 `factor_registry` 先 get revision，再由单一入口登记完整 Portfolio，并原子维护文件 | 机器状态只有唯一写入入口，写前检查 revision，持久化采用原子替换 | `factor_registry` MCP、portfolio Viewer | 继续使用 `ds_lite_state.py` 的 lock、expected revision 和 atomic replace | core |
| `LegacyFinancialFactorPortfolio` 明确为只读 compatibility shape，不能视为 registered portfolio | legacy 数据可以恢复阅读，但不能静默升级为当前已验证状态 | 旧 portfolio schema 和因子状态 | Graph v1/旧 artifact 保持兼容读取；typed evidence/review 缺失时 fail closed | core |
| portfolio 保存 blockers、current batch/判断与 nextActions | 中断后必须从项目文件恢复阻塞、当前判断和下一动作 | batch、financial stage/status | work unit、Graph active route、STATUS 与字符串 `next_action` | core |
| skill 要求先选择机制方向，再消耗模拟；相近候选优先做局部变化 | 先写机制假设，再做最小判别 probe；优先单轴 ablation（single-axis ablation） | 字段、窗口、decay、neutralization | Factor Card `minimal_test` 与 idea 分支；不自动运行循环 | core |
| skill 与项目账本保留失败诊断、discard/blocked 决定 | failed checks 和负结果继续定义搜索边界 | WQ failure codes、PnL/相关性 | Graph branch/rollback/supersedes、negative evidence、review claim assessment | core |
| Financial Factor Mode 定义专用 stage/status、settings、metrics、expression 和 portfolio | 这些字段只对金融案例成立 | Finance stage/status、市场、股票池、表达式、WQ/Qlib 指标和阈值 | 仅作为审计与教学 fixture，不进入 runtime/template schema | fixture |
| mode 提供 continuous、submit_qualified、外部提交和 registry/Viewer | Lite 不拥有长期调度、数据库或外部提交生命周期 | `factor_registry` MCP、portfolio viewer、continuous mode、自动 Git checkpoint、external submission | 不映射；保持 OpenScience/用户为上层 owner | reject |

## Finance residue 与 reject 清单

以下内容不得进入 Lite core、默认模板或默认 skill：

- Finance stage/status、因子表达式、market/region/universe、股票池和持仓参数。
- WQ BRAIN、Qlib、Sharpe/Fitness/turnover/相关性阈值及 external submission 语义。
- `factor_registry` MCP、portfolio viewer、数据库、continuous mode、自动 Git checkpoint。
- 自动提交、自动状态轮询、后台重试和把 submit/pending 直接写成 verified/active 的路径。

## AGPL 隔离边界

Lite 的 Apache-2.0 源码不复制上游 AGPL 代码、schema、类型、skill 正文或自动化实现。本次只记录可观察事实与抽象关系，并用 Lite 现有接口独立表达。上游文件仅用于审计，不进入插件包、测试 fixture 或教学材料；金融专名只允许出现在本审计、NOTICE、迁移说明和领域词扫描的拒绝列表中。

## 验证状态

- `git ls-remote` 已核对 tag 与解引用 commit。
- `git ls-tree` 已核对三个 blob；上游 skill、linked reference、Financial Factor model source、LICENSE 与 NOTICE 已只读审计。
- `tests/test_upstream_transfer.py` 锁定 provenance、AGPL 隔离、迁移规则和 core 领域词扫描。
- 这份审计不验证金融 profile，不授权外部提交，也不把单次教学 pilot 提升为领域支持声明。
