# Nature Skills MCP 与外部服务首次配置

Nature skills 中的文献检索、引用核验、下载、浏览器和部分图表流程可以使用 MCP 或外部 API。它们不是安装插件时自动开启的能力。首次使用时运行：

```text
python <academic-plugin>/scripts/ds_lite_nature_setup.py onboarding --workspace .
```

脚本只检查环境变量是否存在、工具是否在 PATH 中、工作区是否已有本地 MCP 配置，并生成脱敏引导。它不会读取密钥值，不会访问网络，不会修改 `CODEX_HOME` 或全局 Codex 配置。

完整部署依据及上游 `--pull` / `--check` 命令与 DS Lite 的对应关系见 [Nature Skills 上游部署映射](nature-upstream-deployment.md)。DS Lite 使用固定 vendor/runtime 快照模拟一致性检查，不静默同步到全局 `~/.codex/skills`。

## 推荐流程

1. 运行 `inventory` 查看 17 个 nature skill 及上游 commit。
2. 运行 `doctor` 查看当前环境状态。
3. 仅设置实际需要的 API 环境变量。
4. 在工作区 `.ds-lite/nature/mcp-config.json` 中填写已授权的本地 MCP 命令和环境变量名。
5. 运行 `apply` 生成项目级配置模板，再运行 `verify`。
6. 外部检索、下载、浏览器和发布动作仍需在任务中明确授权。

## 状态含义

- `ready`：本地配置和必要工具已观察到。
- `needs-config`：缺少环境变量或项目级 MCP 配置。
- `missing-dependency`：工具未安装或不在 PATH。
- `blocked-by-policy`：动作需要额外授权。
- `not-observed`：当前执行面无法确认，不得当作通过。

## 隐私边界

receipt 只保存状态、环境变量名称、工具可用性和相对 evidence ref。不得保存密钥、完整环境、原始 API 响应、原始 stderr、prompt、隐藏推理或绝对工作站路径。
