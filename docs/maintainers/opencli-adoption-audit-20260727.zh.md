# OpenCLI 采用审计

## 决策

OpenCLI 不进入 Core，不作为 Web 默认后端，也不随插件 vendor。它只作为
Web 包的可选 `opencli-cli` challenger，且只允许 manifest 中同时满足
`access=read`、`strategy=PUBLIC`、`browser=false` 的命令。

## 审计表

| 项目 | 证据 | DS Lite 落点 | 排除项 | 状态 |
|---|---|---|---|---|
| 来源 | `@jackwener/opencli` 1.8.6；Apache-2.0；GitHub/npm URL 已记录 | Web `THIRD_PARTY_NOTICES.md` | 不复制源码和 skill | `passed` |
| CLI 入口 | `opencli --help`、结构化 `--format json` | `ds_lite_extensions.py opencli` | 不把 OpenCLI 作为 Core CLI | `passed` |
| 公开适配器 | manifest `Strategy.PUBLIC`、`access=read`、`browser=false` | manifest 运行前检查 | cookie、UI、profile、auth 命令 | `passed` |
| 浏览器桥 | README 声明 Chrome Bridge、localhost daemon、登录态 profile | 仅记录 capability，不调用 | 不安装扩展、不启 daemon | `not-observed` |
| 来源记录 | Web `source-record.v2` | 输出哈希、相对 artifact、预算、失败层 | 不把 adapter 输出直接升格知识 | `passed` |
| 安全边界 | manifest 和命令参数双重拒绝 | public-only | `browser/auth/upload/form/cookie` | `passed` |
| 真实公开命令 | OpenAlex `search` live 通过；arXiv `search` 在 30 秒预算内超时 | benchmark challenger | arXiv 不宣称成功；继续记录 provider 差异 | `partial` |

## 运行时边界

OpenCLI 的登录态浏览器、Cookie、表单、上传、profile、daemon 和 Chrome
Bridge 不属于 DS Lite Web v1。缺少 OpenCLI、manifest 或公开适配器时，返回
结构化 `not-observed/blocked`，不回退到猜测执行。
