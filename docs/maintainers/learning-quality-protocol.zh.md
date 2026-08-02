# 学习凭证与工业质量门

## 按需示教

Core 维护十篇短教程，技能只声明需要的教程 ID。宿主在第一次写入、执行命令或联网前传入 `active_skill`，Core Hook 随即检查项目内的 `research/learning/<skill>.json`。没有凭证、教程哈希变化或 Core 版本变化时，副作用动作会 `block`；学习 helper 本身是唯一白名单。

教程正文只在首次学习时读取。学习脚本把适用条件、关键规则、易错点、本任务检查表和仍需人工判断压缩为不超过约 600 字的摘要，写入 `research/artifacts/learning/`，机器凭证写入 `research/learning/`。后续 UserPromptSubmit 只注入当前/过期状态和摘要相对路径，不重复注入全文；Stop 会检查本轮明确选择的技能是否留下当前凭证。

## 质量计划

在项目写入 `research/quality/plan.json` 后，PreToolUse 会先校验 `ds-lite.quality-plan.v1`。低风险至少声明 focused test；中风险必须声明 unit、Gherkin 和 coverage，变更行覆盖率至少 80%；高风险还必须声明 mutation、fresh reviewer、recovery 和 security，覆盖率至少 90%，定向变异分数至少 80%。

`research/quality/result.json` 采用 `ds-lite.quality-result.v1`。所有需求必须有已通过证据；测试命令必须实际观察；安全审查始终必需。质量计划存在而结果缺失或不通过时，Stop 会保持阻断。vendor、生成文件或不可执行文档可以排除，但必须写入排除理由和残余风险。

## 外部包

Web 的 `fetch` 只支持公开 HTTP 内容，v2 source record 对成功内容强制哈希和相对 artifact，对失败保留失败层和原因。`doctor` 只发现 Playwright、Firecrawl、agent-browser，不自动安装。Knowledge 的 Tapestry/ScholarAIO `pull-*` 只有读取到真实外部 export 才能报告 passed；否则报告 `blocked/not-observed`。所有 proposal 默认进入 pending review queue。
