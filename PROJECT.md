# DeepScientist Lite Codex Plugin

## 研究背景

本仓库实现一个面向教学、快速启动和小型科研项目的轻量 Codex 插件。它抽取 DeepScientist 工作流中可恢复、可审计、可教学的文件协议，不复制 daemon、Web/TUI、connector、MCP 或长期调度平台。

根目录 `PROJECT.md` 是本仓库的长期项目记忆；`plugins/deepscientist-lite/assets/templates/PROJECT.md` 是插件为用户项目生成的合同模板，两者职责不同。

## 基本假设

- 文件化项目合同、artifact 和显式状态图足以支持短周期科研工作的跨会话恢复。
- 状态内核应保持 Python 3.10+ 标准库实现，避免增加教学部署成本。
- Graph JSON 是机器权威状态，`RESEARCH_MAP.md` 是可重建的人类投影。
- 失败实验、旧路线和公开决策理由应保留，但不得记录隐藏思维链。

## 分析目标

- 可靠维护 intake、scout、idea、experiment、analysis/write 的最小科研闭环。
- 防止并发覆盖、非原子写入、路径泄露和证据关系污染推进路线。
- 保持 Windows 与 Unix-like 环境中的命令、中文和空格路径可用。
- 为教学 Beta 提供可重复验证、迁移和发布流程。

## 工作流程

1. 通过五个 `ds-lite-*` skills 读取项目合同、状态和证据。
2. 先写 artifact、memory 或可复现 `run_*.sh`，再调用状态 CLI。
3. Graph 写操作在锁内检查 revision、校验语义并原子替换。
4. 每次提交后重建 `RESEARCH_MAP.md`；地图可由 graph 修复。
5. 使用统一验证脚本执行单元测试、仓库 smoke 和语法检查。

## 代码结构

- `plugins/deepscientist-lite/`：可安装插件、技能、模板、协议和状态脚本。
- `tests/`：Graph v2、CLI、迁移、并发和路径回归测试。
- `tools/validation/`：仓库级验证器与 shell/PowerShell 入口。
- `docs/`：设计、迁移、已知问题和发布维护资料。
- `teaching/`：不进入运行时包的课程与演示材料。

## 运行流程

- Unix-like：`bash tools/validation/run_validate.sh`
- PowerShell：`powershell -ExecutionPolicy Bypass -File tools/validation/run_validate.ps1`
- 单元测试：`python -m unittest discover -s tests -v`
- 仓库 smoke：`python tools/validation/validate_repo.py`

## 验收标准

- Graph v2 写入具备跨平台锁、revision 检查和原子替换。
- v1 可读且可迁移，原 graph 备份永久保留；外部绝对路径不会被静默写入 v2。
- progression trace 不遍历 `supports`、`blocks` 或 `rollback`。
- 五个技能只通过 CLI 修改 graph，并能处理 revision 冲突。
- Windows PowerShell、Git Bash、WSL DrvFS、WSL ext4，以及远程 Windows/Ubuntu CI 均通过统一验证入口。
- manifest、技能、模板、文档和发布版本保持一致。

## 设计决策

- 当前发布线：`0.2.0-beta.1`，Graph schema 为 `ds-lite.graph.v2`。
- 项目外资源使用 `external://alias/path`，绝对根目录由 `DS_LITE_EXTERNAL_<ALIAS>` 提供。
- 保留 `DeepScientist Lite` 名称，但明确声明为独立、非官方第三方插件。
- v0.2 不引入 MCP、daemon、Web/TUI、模型路由或长期 automation。
- `run_validate.sh` 必须兼容只有 `python3` 的 Unix/WSL 环境；运行时脚本保持 LF。
- 状态内核模块化属于 v0.2 之后的内部重构，必须保持 Graph v2 与 CLI 兼容。

## 已废弃方案

- Graph v1 的直接覆盖写入与无 revision 并发模型。
- 在 Python 中硬编码初始化文件，与 `assets/templates/` 形成双重来源。
- 使用所有边计算 Active Route。
- 在 graph 中保存项目外绝对路径。
