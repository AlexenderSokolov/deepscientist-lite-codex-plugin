# DS Lite 控制面 Phase 5 实施状态

最后更新：2026-08-01

## 当前阶段

Phase 5 正在进行最终 candidate-bound 聚合。权威前置收据为
`research/.validation-tmp/control-plane-phase4-final-20260801-10/phase4-decision.json`，
SHA-256 为 `83e32bb80a20989161412fc83ff85736f85ab7b8c50479da046cb7b7dc611f5a`。
该收据仅允许建立 Phase 5 目标；在最终双聚合实际通过前，当前项目仍为
`release_allowed=false`。

当前分支为 `codex/nature-provider-hook-acceptance-20260724`。开始 Phase 5 时工作树包含
57 个已跟踪修改和 163 个未跟踪根，共 220 项状态记录。全部内容均视为受保护的用户本地工作，
不得 reset、clean、覆盖或删除。

## 已实现并观察

1. runtime pin 已改为现场验证所选 Codex binary、生成 schema manifest 与 schema bundle；
   stable `0.146.0` 新 action 使用 `run_codex_action_v2`，v1 workflow 注册语义保持不变。
2. Windows/WSL runtime、资源、DBOS 2.28→2.29、用户级 supervisor、真实进程混沌、
   loopback stream disconnect 和 synthetic-provider 429/5xx 已生成通过的原始收据。
   这些证据尚须绑定最终 candidate digest，不能直接提升为发布通过。
3. fresh matched-effect pilot
   `research/.validation-tmp/phase5-matched-effect-20260801-15/windows/results/effect-report.json`
   已实际得到 `descriptive-improvement-supported`：18 个逻辑调用、12 个匿名 arm/case
   组合、一次 projectless Desktop 盲审；双对照 favorable expression dimensions 为 4，
   unsupported completion 未增加，task correctness 无实质退化。
4. 候选冻结前高风险测试 120/120 通过；锁定 Python `3.13.5`、DBOS `2.29.0`
   环境下仓库全量测试 773/773 通过；仓库 validator 已通过。
5. 当前候选已实际观察 stable `0.146.0` 的单 turn Hook 修复、fresh Desktop task、
   四个公开 Academic provider、Windows/WSL 资源和 backup v5 restore。OpenScience producer
   与 fresh-host producer 的 schema 已统一；Core identity 已排除 `__pycache__`，避免运行时
   字节码缓存造成错误候选漂移。
6. legacy 15-gate 使用确定性兼容适配器：历史 execution-surface receipt 必须与至少一份
   当前候选证据共同输入，输出保存全部原始 SHA；不得只复制历史 `status=passed`。

## 最终候选兼容修复

候选 `b45bd224...f62015c` 的收口检查发现，Codex stable `0.146.0` 随附的官方
`plugin-creator` validator 不接受显式 `hooks` manifest 字段，也拒绝 Academic 的旧版
agent metadata 和位于 `skills/` 下的非技能共享目录。隔离实验已证明移除 manifest 字段后
stable host 仍从 `hooks/hooks.json` 自动发现 `UserPromptSubmit`，因此该冲突可通过候选修复，
不能用 validator 豁免处理。

Core 源码保留已验证 identity；确定性发布包 builder 仅移除冗余 `hooks` manifest 字段，
并证明宿主目录自动发现仍保留四事件 Hook 配置。Academic agent metadata 迁移到 stable
`interface/policy/dependencies` 合同，共享层改为隐藏的 `.nature-shared` 支持目录。
发布 staging 保留可安装的 `.agents/plugins/marketplace.json` 与 `plugins/<package>` 布局；
官方 validator 必须对 builder 生成的六个 split packages 全部通过。上述修改会产生新的 source/package digest；
旧候选与其成功、失败 receipt 全部保留，但不再作为最终发布候选。新的候选冻结、真实 Hook、
fresh Desktop、OpenScience、完整回归和双 aggregate 均须重新绑定后才能写 Phase 5 go。

## 当前执行顺序

1. 冻结包含当前实现与本状态投影的最终 source manifest，并保持六包 package digest 不变。
2. 为该 digest 生成全部 16 个 Phase 5 receipt 与 legacy 15-gate 兼容 receipt。
3. 运行全量回归、六包、八安装矩阵、脚本语法、旧收据 hash 与 backup v5 检查。
4. 运行 legacy 15-gate aggregate 和 `[phase4-real-gate, phase5-real-host]` 控制面聚合。
5. 仅由确定性 final assembler写入
   `research/.validation-tmp/control-plane-phase5-final-20260801-01/phase5-decision.json`；
   发布动作保持未执行，结论以该 write-once receipt 为准。

## 尚未观察

- 同一最终 candidate digest 下全部 16 个 revalidation receipt 和 `phase5-real-host` gate。
- 同一候选的 fresh Desktop OpenScience terminal host receipt 与完整 15-gate aggregate。
- `phase5_decision=go` 和 `release_allowed=true` 的 write-once 发布资格收据。

这些项目在产生真实 artifact、hash 和 write-once receipt 前均不得表述为已通过。
