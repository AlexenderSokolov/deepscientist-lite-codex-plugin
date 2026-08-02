# Nature Skills 依赖与副作用边界

每个 nature skill 的完整上游资料保存在固定 commit vendor 快照中；入口旁边的 `provenance.json` 记录来源文件、hash、依赖信号和适配范围。

## 本地层

写作、润色、审稿、回复、提案、阅读和部分统计流程可以只使用工作区文件与 Python 标准库。缺少外部服务时，优先使用 skill 声明的本地 fallback，并把未观察能力写成 `not-observed`。

## 外部层

MCP、文献数据库 API、下载器、浏览器/CDP、LaTeX、Node 和第三方 Python 包都属于独立执行面。它们必须经过首次 onboarding、环境检查和用户授权；插件不自动安装依赖、不自动写全局配置、不自动保存凭据。

## 失败处理

网络失败、认证失败、限流、协议错误、缺少工具、路径或编码错误都保持终态冻结。失败不能被自然语言“完成了”覆盖，也不能自动重试或升级为真实 provider、Hook 或 release 通过。
