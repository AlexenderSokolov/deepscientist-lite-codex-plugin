# codex-autoresearch 集成审计

## 上游与授权

| 项目 | 记录 |
|---|---|
| 仓库 | https://github.com/congwa/codex-autoresearch |
| 固定 commit | `f2389bffbb4cd7789deb6796bc4ba35bf31f2a90` |
| npm 版本 | `0.1.5-beta.0` |
| 许可证证据 | `package.json` 声明 MIT；根目录许可证文件仍需继续核对 |
| 使用授权 | 作者已明确允许自由选用、修改和集成 |
| 当前处置 | `adopted / adapted` |
| 是否复制源码 | `yes`，仅复制已获授权的固定快照，保留来源和许可证说明 |
| vendor 路径 | `plugins/deepscientist-lite/vendor/codex-autoresearch/f2389bffbb4cd7789deb6796bc4ba35bf31f2a90` |

## 保留与适配

| 上游组件 | 处置 | DeepScientist Lite 适配 |
|---|---|---|
| README/workflow | adapted | 映射为 DS Lite 的 bounded continuation 与交接协议 |
| completion protocol | adapted | 增加冻结目标、证据门、acceptance gate 和失败冻结 |
| job loop | adapted | 前台、有界轮次、零自动重试、超时终止 |
| planning/policy/state | adapted | 显式 workdir、state-dir、sandbox、approval 和脱敏 receipt |
| Codex engine | adapted | 固定 CLI、argv 传递、子进程/管道状态归约 |
| CLI/package | adopted/adapted | 保存来源源码并接入 `fake`、`native-codex`、`codex-autoresearch` adapter |
| shell wrapper | adapted | 只保留 ASCII 参数编排，不嵌入 Python 或多行源码 |
| TypeScript tests | adopted as source evidence | 不直接替代 DS Lite unittest，另写边界测试 |

保留的核心能力：冻结目标、完成信号、会话 continuation、状态模型、计划和结果对账。

## 明确拒绝的默认行为

不采用无限循环、隐式 retry、daemon、queue、后台 scheduler、自动 tmux、默认高权限、原始日志、绝对路径、自动外发和静默全局配置修改。原因是这些行为会破坏 DS Lite 的可审计性、隐私边界或重复风险控制。

## 追踪矩阵

| 上游概念 | DS Lite 实现 | 证据 |
|---|---|---|
| frozen goals | `ds-lite.loop-contract.v1` | `tests/test_loop_runner.py` |
| completion gate | evidence gate + summary verify | completion-without-evidence 测试 |
| bounded continuation | `plugins/deepscientist-lite/scripts/ds_lite_loop.py` | fake partial-to-completed 测试 |
| fail-closed stop | 固定 failure class 和 acceptance gate | ambiguous/timeout/duplicate-risk 测试 |
| source provenance | vendor snapshot + audit table | `tools/validation/upstream_manager.py verify` |
| secret-safe state | 脱敏 receipt | secret marker exclusion 测试 |

## 当前状态

离线 Loop acceptance 已通过；真实 provider、完整 Hook、真实 child-agent delegation、matched effect、formal cache、fresh Desktop 和 release gate 仍未验证。离线结果不能解锁真实门。
