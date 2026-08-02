# 跨学科技能设计原子审计

## 结论

本轮不移植任何上游仓库，不复制提示词，也不把完整科研系统塞进 Core。采用单位是“设计原子”：先过 `core / profile / fixture / reject` 分类门，再由本仓库重新定义协议、措辞和测试。机器可审计身份见 `evaluation/cross-disciplinary-upstreams.json`；旧单体的 `upstream-project-registry.json` 保持冻结。

## 设计原子矩阵

| 上游 | 分类 | 采用 | 落点 | 明确排除 |
| --- | --- | --- | --- | --- |
| ARS-Codex | profile | clean-room | Academic 引用状态、多索引交叉证据、阅读范围与 claim 定位 | CC BY-NC 文本、Material Passport、Hook、团队 runtime |
| Claude Scholar | profile | companion | Knowledge 的 Sources 到 Knowledge 审阅晋升边界 | 第二套 KB、Nature 重复入口、默认 Hook |
| AI-Research-SKILLs | fixture | deferred | 第二批 AI 包需求与案例来源 | 90+ catalog、整仓镜像 |
| Auto Empirical | fixture | fixture-only | 实证阶段、失败诊断与 Golden Workflow 测试需求 | CC BY-SA 聚合内容、嵌套 skill/runtime |
| Scientific Agent Skills | profile | deferred | 第二批 RDKit/Scanpy 专业适配器候选 | 148 个入口和专业运行时 |
| codex-claude-academic-skills | profile | clean-room | Engineering 的 FFT、窗函数、分辨率、单位、图轴检查 | Office、论文写作重复入口 |
| ARIS | fixture | clean-room | Academic fresh review、修订白名单、单一最强反对意见 | 无人值守循环、monitor、MCP、自动数据 |
| Kim_Service | fixture | fixture-only | 维护层的核心问题门、触发评测、baseline 和真实证据 | Memory/Goal/Decision/Teams 等重复状态机 |

## 许可证边界

ARS-Codex 与 Auto Empirical 的许可证约束不适合把内容并入 Apache-2.0 运行时；本轮只使用公开功能描述形成独立需求和测试。MIT 上游同样没有被直接复制，因为减少重复入口和状态机比许可证许可更重要。所有登记项的 commit、根 README/许可证 SHA-256 与采用结论都固定在 evaluation registry 中。

## 未进入本轮

Core 苏格拉底模式仍等待真实 Hook、delegation、matched effect、formal cache 与 fresh Desktop 五类门关闭。AI-Research、RDKit 和 Scanpy 仅保留孵化候选，不应从本文推断为已支持能力。
