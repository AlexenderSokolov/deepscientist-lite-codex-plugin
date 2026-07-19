# 产品定位与长期记忆

## 主要工作

DeepScientist Lite 是一个 Codex 插件项目。它的目标很具体：不部署完整 DeepScientist 平台，也能把核心科研协议教会、用起来。

插件本身才是产品。教学案例和小型实验是验证材料，不是产品的替代品。

## 什么算插件进展

- 技能能被发现、能被触发，而且描述足够简洁。
- 文件协议在新项目和旧项目中都容易初始化。
- `ds_lite_state.py` 能在不记录隐藏 chain-of-thought 的前提下，让状态保持可追踪。
- 用户遇到安装、缓存或编码问题后，仍有办法恢复。
- 教师可以在 20-30 分钟内讲清核心流程，并运行 45 或 90 分钟的证据/审查课程。
- 学生可以跑完一轮项目流程，并在事后看懂路线怎样走过来。

## 实验用来回答什么

实验用来检验插件能不能保住研究状态、失败和主张。它们可以做教学演示，但不能把插件变成算法基准仓库。

经过脱敏的范式比较案例展示了 DS Lite 如何记录一条真实路线：查来源、选 idea、记录实验结果、保留负证据，再说明下一步为什么这样选。

## 当前版本判断

`v0.5.0-beta.2` 是沟通审计和源码包预发布版本。它保留 Graph v2 与 Evidence Pack v1，增加可选 `STYLE.md`、四个沟通 profile、渐进式叠加层、受保护内容规则、固定提交的上游审计快照、`ds-lite.communication-audit.v1`，以及覆盖七个 skill 的确定性四事件 hook 适配器。

源码包验证可以作为发布证据；但 fresh cache installation、新线程中的七技能发现、four-profile 行为、真实主机上的 hook 注册/阻断，以及 human A/B 结果，目前都明确未验证。

2026-07-19 的验收进一步确认：Windows PowerShell、Git Bash 和 WSL 各运行 99/99 单测，仓库 validator 与 `py_compile` 通过；F 盘隔离 acceptance package 已静态审计并安装到隔离 `CODEX_HOME`，七个 skill 目录可见。真实 `codex exec` canary 在 214 秒内没有事件、最终反馈或 usage，按 fail-closed 规则冻结，因此七个 fresh-agent 测试和四组人工 A/B 没有启动。详细记录见[验收记录](acceptance-beta2-20260719.zh.md)。

hook 不会由 manifest 自动启用。注册器必须先展示拟写入的变更；如果官方宿主文档或真实验收运行无法确认配置格式，就返回 `host_supported: false`，不写任何配置。有效审计可以阻断无证据的完成措辞、保留失败记录，但不能证明科学结论为真，也不能推断模型意图。

P0 source validation 覆盖 `ds-lite.work-unit.v1`、typed Evidence Pack promotion、`ds-lite.review-result.v1`、claim readiness、evidence detail 和 route-scoped waiting。这些仍然只是源码包证据：installed cache remains unverified，不能从源码树推断缓存已经更新。P1 action/receipt 和 P2 typed external-long profile 不属于当前 P0 声明。

手动 tmux 容量握手仍然等待发布证据，维护状态标签为 `manual tmux capacity handshake remains pending release evidence`。至少需要：用户创建的固定 socket 通过真实断开/重连探测；socket 缺失时能干净停止且不调用 `new-session`；pane-scoped Codex CLI child worker 能把 provider 查询/恢复证据与 tmux、实验恢复证据分开记录。

之前的 `v0.3.0-beta.1` 证据审查教学 beta 仍是有用的历史材料：2026-07-05，当时的 36 个本地测试、仓库 smoke、Windows PowerShell、Git Bash、插件验证器和六个 v0.3 skill validator 均通过。但那份证据不能证明 v0.4 缓存安装或 `$ds-lite-iterate` 行为。详见[强化记录](v0.3-hardening-log.zh.md)和[Codex 验收审计](v0.3-codex-acceptance.zh.md)。新提交的远程 CI、明确的缓存安装、review/analysis/iterate 主恢复路线、独立教学报告、macOS 验证和可重复的缓存升级恢复，仍需另行补齐。

## 长期记忆规则

- 会影响后续维护的插件决策写在本文、`known-issues.md`、`release-checklist.md`、README 和案例文档中。
- 算法实验细节留在对应案例或宿主研究项目，不要塞进产品定位文档。
- 不增加 MCP、daemon、Web/TUI。beta.2 hook 适配器是用户确认、宿主受限的可选能力，不改变 manifest，也不创建 daemon。
- 教学案例只能证明教学价值；只有暴露插件流程缺陷时，才把它作为发布阻塞项。
