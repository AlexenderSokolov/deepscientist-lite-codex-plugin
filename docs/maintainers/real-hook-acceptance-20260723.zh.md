# 真实 Hook Host 验收记录（2026-07-23）

## 本轮目标

在不读取或改写旧 `communication-beta2-20260720-gated-02` 的前提下，验证候选插件是否由 pinned Codex 0.144.5 的 fresh isolated host 加载，并观察四类 Hook 事件。完整通过条件是：UserPromptSubmit=allow、PreToolUse=block、PostToolUse=allow、Stop 首次 block 后一次 allow。

## 实际观察

- `communication-beta2-20260723-trusted-hook-02`：CLI 任务通过，记录四类事件，但四类决定均为 `allow`。workspace 为空，因此只证明事件路径被调用，不证明阻断策略。
- `communication-beta2-20260723-trusted-hook-03`：同一空 workspace 的 fresh 任务仍为四类 `allow`；不升级为完整 Hook 验收。
- `communication-beta2-20260723-trusted-hook-04`：fixture 首次实现使用了未注册的 iteration action kind，准备失败；该身份冻结，不重试或覆盖。
- `communication-beta2-20260723-trusted-hook-05`：fresh workspace 成功初始化 DS Lite 状态和 running iteration。真实 CLI 启动并加载 Hook，观察到 UserPromptSubmit、PreToolUse、PostToolUse；任务随后在 `turn.failed` 终止，PreToolUse 没有 `block`，Stop 没有事件，故完整 Hook gate `blocked`。

证据目录：

- `.validation-tmp/communication-beta2-20260723-trusted-hook-02/hook-host.json`
- `.validation-tmp/communication-beta2-20260723-trusted-hook-03/hook-host.json`
- `.validation-tmp/communication-beta2-20260723-trusted-hook-04/preparation.json`
- `.validation-tmp/communication-beta2-20260723-trusted-hook-05/hook-fixture.json`
- `.validation-tmp/communication-beta2-20260723-trusted-hook-05/hook-host.json`

receipt 只保存事件类型、决定、计数、CLI 身份和脱敏失败分类；不保存 prompt、原始 JSONL、stdout/stderr 或凭据。

## 当前结论

`trusted-hook-05` 提供了真实 Hook loader 的部分证据，但没有证明危险操作阻断，也没有证明 Stop 一次续行。真实 delegation、matched effect、formal cache、fresh Desktop 和 release gate 继续保持 `not-verified`。

## 自动化改进

新增 `teaching/trusted_hook_fixture.py`、`run_trusted_hook_host_acceptance.ps1` 和 `.sh`。入口通过 argv 准备 fresh workspace 和 running iteration，不嵌入 Python 源码，不执行破坏性命令，已有输出拒绝覆盖。后续真实 Hook 尝试必须使用新身份；任何失败冻结当前身份。

## 验证

- 定向离线与协议测试：`38/38` 通过。
- 完整 unittest：`289/289` 通过。
- 跨系统验证：`status=passed`；缺少的 PowerShell 7、WSL Bash 或 shellcheck 保留为 `not-observed`。

唯一下一步：若要继续真实 Hook，先修正任务设计以让 Codex 产生可观测的 graph 直接编辑尝试，再使用全新身份单次执行；不得重放 `trusted-hook-05`。
