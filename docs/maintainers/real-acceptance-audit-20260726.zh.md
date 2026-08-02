# DeepScientist Lite 0.8 真实验收审计表

本表记录本轮新身份、新临时根和新产物。旧 pilot、旧 cache 和旧 receipt 不自动继承。`passed` 只表示该行自己的证据通过；相邻证据不能推断其他门。

| 门 | 本轮证据 | 状态 | 阻塞/下一动作 |
|---|---|---|---|
| Source / offline | 六包源码矩阵；`G:\DS-Lite-validation\offline-acceptance-20260726\offline-acceptance.json` | `passed`（离线/源码范围） | 不代表真实宿主 |
| Web stdlib HTTP | `G:\DS-Lite-validation\web-real-20260726\research\artifacts\static.json`、`pdf.json` | `passed`（静态 HTML、PDF） | RSS DNS 失败、中文站 TLS/连接失败，均已生成 failed source-record |
| Web 宿主浏览器 | Codex In-app Browser：Example、W3Schools JS iframe、W3 PDF 成功；RSS 错误页；中文 Wikipedia 被网络层拒绝 | `partial` | 需为宿主结果补全统一 benchmark receipt；Playwright CLI 当前未发现 |
| Web Playwright | doctor 报 `playwright-cli=false` | `not-observed` | 用户授权后安装并跑 10 案例；未授权前不安装 |
| Web Firecrawl | doctor 报 `firecrawl=false` | `not-observed` | 需要用户 API、外发和费用批准；不阻塞公共 HTTP |
| Web agent-browser | doctor 报 `agent-browser=false` | `not-observed` | 作为 challenger，需另行安装/授权 |
| Hook 协议 | `tests/test_user_action_protocol.py`、`tests/test_communication_hook.py`、四事件离线 helper | `passed`（源码/离线） | 真实 trusted host 未启动 |
| Hook 真实宿主 | 新 pilot `trusted-hook-20260726-01` | `not-observed` | 缺 pinned `CODEX_BIN`；已生成 `G:\DS-Lite-validation\user-action-request-trusted-hook-20260726-01.json` |
| Long task / tmux | `G:\DS-Lite-validation\external-tmux-plan-20260726.md` | `awaiting-user-bootstrap` | 用户在独立 WSL shell 执行 bootstrap，回传 socket/server/pane fingerprint；当前 WSL 列表访问被系统拒绝 |
| Delegation | 离线 worker-a/worker-b result refs；真实 host 未启动 | `not-verified` | provider canary 和 trusted host 通过后启动两个互斥 child，再跑 partial child |
| Matched effect | 离线 4-case × 3-arm fixture 已冻结；真实 12 arm 未调用 | `not-verified` | 取得真实 provider/host 后完成预注册调用和盲评 |
| Formal cache | 本地源码矩阵通过；marketplace/fresh cache 未重装 | `not-verified` | 标准 marketplace 安装六种矩阵，重启 Desktop，验证卸载残留 |
| Fresh Desktop | 未创建 fresh Desktop task | `not-observed` | 用户在 OpenScience/Codex Desktop 创建 fresh task 并回传 task ID |
| OpenScience | `F:\OpenScience\OpenScience.exe` 存在；未取得 task ID | `not-observed` | 用户创建 Core+Web+Knowledge fresh task，回传 task ID |
| Academic real providers | 代码/fixture 已完成；Crossref/OpenAlex/S2/arXiv 本轮未真实调用 | `not-verified` | 需要 provider 外发授权和新 live-provider pilot |
| Release gate | 尚未聚合 v2 全部独立 receipts | `blocked` | 所有非 `passed` 行关闭后才可提交、合并、发布 |

## 已实际执行的本轮动作

1. 修正 trusted fixture 使用 `plugins/deepscientist-lite-core`。
2. 统一 trusted Hook、loop、cross-system、nature 和 Web 脚本读取 `TEMP_ROOT`。
3. 新增 `ds-lite.user-action-request.v1` / `v1 response`，Hook 会在 provider、浏览器、tmux、delegation、宿主/发布动作前强制生成请求并阻断。
4. 恢复 Core communication audit、权限提升阻断、Stop 完成声明校验和 installer 兼容输出。
5. 运行用户动作协议 4/4、通信 Hook 11/11、包矩阵 11/11、Web 协议 15/15；Web 包完整入口通过。
6. 真实宿主浏览器访问静态 HTML、JS 渲染页和公开 PDF；失败页面与网络层也记录，不重试污染身份。

## 用户现在必须提供/执行

- `CODEX_BIN` 完整路径、pinned 版本和 SHA-256，才能启动真实 trusted Hook/provider pilot。
- 在独立稳定 WSL shell 执行 `G:\DS-Lite-validation\external-tmux-plan-20260726.md` 中的 bootstrap，并回传 socket、server fingerprint、anchor/workload pane。
- 若要继续 Playwright：明确允许安装 CLI/浏览器运行时。
- 在 OpenScience GUI 创建 fresh task，安装 Core+Web+Knowledge，并回传 task ID。
- 若要跑 Firecrawl：提供 API 授权、费用和公开数据外发批准。
