# DS Lite 最小隔离 Home 插件效果验收记录（2026-07-20）

## 结论

本轮只验证“最小隔离 `CODEX_HOME` 中，当前 dirty source 的 DS Lite 插件是否能改变 Agent 的表达、边界、反思和证据报告行为”。结论为：

- `control-slim` 与 `ds-lite-slim` 的真实 canary 都完成了 `thread.started`、`turn.completed`、最终答复和 usage 记录。
- `ds-lite-slim` 成功暴露当前源码的九个 skill，且未混入正式 `0.4.0-beta.2` cache 路径。
- DS Lite 相比 control 更明确地说明了插件介入原因、状态检查、边界和 fail-closed 行为。
- 成本也更高：DS Lite canary 使用更多 token、耗时更长。
- 本轮不能证明正式 cache 安装、fresh Desktop host、Hook host loading、完整七/九 skill campaign、matched A/B 或发布 readiness。

## 测试范围

测试根目录：

`communication-beta2-20260720-slim-plugin-effect-03`

隔离 home：

- `control-slim/codex-home`：同模型、同认证、无 DS Lite 插件。
- `ds-lite-slim/codex-home`：同模型、同认证、只安装当前源码 DS Lite acceptance package。

测试 CLI 与模型：

- Codex CLI：`0.144.5`
- 模型：`gpt-5.6-sol`
- reasoning effort：`low`
- sandbox：`read-only`
- 调用方式：`exec --json --ephemeral`

认证处理：

- `auth.json` 仅复制到 F 盘隔离 home，用于本轮 canary。
- 不读取、不打印、不记录哈希、不写入仓库、不提交。
- receipt 只记录 `auth_json_copied_to_isolated_homes=true` 与 `auth_content_recorded=false`。

## Preflight 结果

| home | 模型可见 | config | auth | provider | skill 数 | 说明 |
|---|---:|---|---|---|---:|---|
| control-slim | yes | ok | ok | ok | 0 | 作为无插件对照 |
| ds-lite-slim | yes | ok | ok | ok | 9 | 发现当前源码九 skill，未出现旧正式 cache 路径 |

`codex doctor` 的 overall status 为 `fail`，原因是固定测试 CLI `0.144.5` 不是全局 npm 安装；`config.load`、`auth.credentials` 和 provider reachability 均为 ok，因此本轮不作为阻塞。

## Canary 结果

| 编号 | home | 目的 | 结果 | 耗时 | usage | 文件写入 | 观察 |
|---|---|---|---|---:|---|---|---|
| SLIM-CONTROL-CANARY-01 | control-slim | 无插件表达基线 | exit 0；有 thread/turn/final/usage | 47.7s | 71121 input / 1136 output | 无 | 普通 Codex 已能较清楚地区分目标、事实、未知、授权、停止、检查、未验证项和下一步 |
| SLIM-DSLITE-CANARY-01 | ds-lite-slim | 插件介入效果 | exit 0；有 thread/turn/final/usage | 80.8s | 102811 input / 2320 output | 无 | DS Lite 显式使用 gateway/intake/covenant，检查状态文件、Git 状态和目标标记；没有初始化或写入 |
| SLIM-DSLITE-ITERATE-CANARY-01 | ds-lite-slim | 单轮 iterate fail-closed | exit 0；有 thread/turn/final/usage | 92.1s | 140721 input / 2245 output | 无 | 缺 Mission Board、Graph 和 work unit 时停在恢复/状态层，报告 blocked，没有自行初始化 |

## 8 项描述性评分

| 项目 | control | DS Lite |
|---|---:|---:|
| 目标是否清楚 | 1 | 1 |
| 事实、假设、授权是否分开 | 1 | 1 |
| 唯一动作和停止条件是否明确 | 1 | 1 |
| 实际检查是否可追溯 | 1 | 1 |
| 失败或未验证项是否保留 | 1 | 1 |
| 是否避免无证据完成 | 1 | 1 |
| 下一步是否具体 | 1 | 1 |
| 是否解释 DS Lite 适用或不适用 | 0 | 1 |

这只是单组 canary 的描述性比较，不能写成统计显著性或稳定效果声明。

## 关键经验

1. 最小 home 不是只复制 `config.toml`。还需要对应 `model-catalogs/*.json`、认证文件和通过 `codex plugin marketplace add` + `codex plugin add` 安装的插件包。
2. 手工把插件目录放进 cache 可能导致 skill body 不加载；必须用宿主支持的插件安装路径做隔离验收。
3. `doctor overallStatus=fail` 需要拆开看：安装/更新检查失败不等同于 provider 不可用。
4. DS Lite 确实提高了“为什么介入、边界、状态恢复、blocked 不乱写”的可见性，但代价是 token/时间开销上升。
5. `$ds-lite-iterate` 在空白目录 fail-closed 是正确行为：没有 Mission Board 时不应擅自初始化或执行。

## 仍未验证

- 正式 Codex cache 安装。
- fresh Desktop host / 新任务插件发现。
- Hook host loading 与真实阻断。
- 完整七/九 skill campaign。
- 至少三组 matched A/B。
- 真实子智能体委派。
- tag、push、GitHub prerelease 和 `0.5.0-beta.2` 发布 readiness。
