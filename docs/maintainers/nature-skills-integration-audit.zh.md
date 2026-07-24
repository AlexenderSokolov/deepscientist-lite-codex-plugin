# nature-skills 全量整合审计

## 上游身份

| 字段 | 记录 |
|---|---|
| 仓库 | https://github.com/Yuan1z0825/nature-skills |
| 固定 commit | `91862221b39f7ca16d52ae0e1e9cb6c2bb31a96b` |
| 许可证 | Apache-2.0 |
| 快照 | `plugins/deepscientist-lite/vendor/nature-skills/91862221b39f7ca16d52ae0e1e9cb6c2bb31a96b` |
| 文件规模 | 固定快照实际观察为 606 个文件 |
| 整合范围 | 17 个可发现 skill，`nature-shared` 为内部共享层 |
| 当前处置 | `adopted / adapted` |

## 完整保留内容

每个 skill 保留原始 `SKILL.md`、manifest、静态 fragments、references、scripts、templates 和 tests。运行时入口在原始正文前增加 DS Lite 生命周期、依赖检查、授权边界和 provenance；没有把上游工作流改写成摘要。

已整合：academic search、citation、data、downloader、experiment log、figure、literature pipeline、paper-to-patent、paper2ppt、polishing、proposal writer、reader、reference verifier、response、reviewer、statistics、writing。

## 适配内容

- 所有入口执行 DS Lite `start / progress / end`。
- MCP、外部 API、浏览器、下载、LaTeX、Node 和 Python 依赖先经过 workspace onboarding。
- 密钥只检查环境变量存在性，不读取或保存值。
- 外部动作需要明确授权；缺依赖记为 `not-observed`。
- 路径通过 argv 传递，receipt 只保存相对引用和脱敏状态。
- `nature-shared` 不进入 skill discovery。

## 不自动启用的内容

不自动注册 MCP、不修改全局 Codex 配置、不自动安装依赖、不自动保存凭据、不自动下载或发布。对应能力通过 `ds_lite_nature_setup.py` 生成工作区级配置和中文新手引导。

## 证据

- `plugins/deepscientist-lite/references/nature-skill-registry.json`
- `plugins/deepscientist-lite/references/nature-upstream-deployment.md`
- 每个入口目录的 `provenance.json`
- `tests/test_nature_integration.py`
- `tests/test_nature_setup.py`
- `tests/test_nature_runtime_acceptance.py`
- `teaching/nature_runtime_acceptance.py`
- `tools/validation/upstream_manager.py verify`

## 未验证项

真实 MCP 宿主加载、真实第三方 API wire compatibility、浏览器/CDP、下载器、LaTeX、Desktop、provider、Hook、delegation、matched effect、formal cache 和 release gate 仍未验证。源码与离线测试通过不等于真实外部服务通过。
