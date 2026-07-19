# 沟通层上游逐文件采用审计

> 状态：`0.5.0-beta.2` 源码审计资料；`runtime_loaded: false`。

本文逐文件记录三个固定提交的用途、哈希、采用结论、本地落点和拒绝边界。
完整快照用于离线复核，不由七个科研 skill 直接加载。目录项没有被省略；
二进制资产只验证字节和哈希，具名作者档案只审读、不运行。

## 判定规则

- `化用`：保留方法和可检验规则，用 DeepScientist Lite 的原创表达重新组织。
- `拒绝运行时采用`：文件仍完整保存和审读，但其人格模仿或其他内容不进入运行时。
- `仅元数据/许可证/资产`：只服务来源、法律或完整性审计。
- 每一行必须与 `upstream-adoption.json` 一致；验证器发现遗漏、重复或哈希漂移即失败。

## `AIScientists-Dev/academic-humanizer@94b88b23`

| 源文件 | 用途 | SHA-256 | 结论 | 本地落点 | 逐文件说明 |
| --- | --- | --- | --- | --- | --- |
| `.gitignore` | 仓库元数据或维护配置 | `cf237c7aff44efbe...` | 仅元数据 | `docs/maintainers/upstream-adoption-audit.zh.md` | 仅用于来源、版本、构建或分发审计；不转化为运行时表达规则。 |
| `LICENSE` | 许可证 | `95201f07cd5d4454...` | 仅许可证 | `plugins/deepscientist-lite/THIRD_PARTY_NOTICES.md`<br>`NOTICE` | 逐字保留许可证和版权声明，并用文件哈希验证；不把许可证改写成通用模板。 |
| `README.md` | 用户或版本文档 | `ed40692dbee51ed2...` | 化用 | `plugins/deepscientist-lite/references/communication/academic-writing.md`<br>`docs/maintainers/upstream-adoption-audit.zh.md` | 化用学术伦理、披露、个性化和非检测规避边界。 |
| `SKILL.md` | 运行时规则入口 | `1f4501cb7331cffe...` | 化用 | `plugins/deepscientist-lite/references/communication/academic-writing.md`<br>`plugins/deepscientist-lite/references/communication/self-audit.md` | 完整化用六层学术规则、claim-evidence、proposal feasibility 和变更报告。 |
| `assets/banner.svg` | 视觉资产 | `e3a332cac2dcb74c...` | 仅资产 | `docs/maintainers/upstream-adoption-audit.zh.md` | 仅作资产完整性和哈希审计，不从图片或 SVG 推导写作规则，也不加载到运行时。 |
| `assets/rednote-zh.png` | 视觉资产 | `cf1ada64d95deef0...` | 仅资产 | `docs/maintainers/upstream-adoption-audit.zh.md` | 仅作资产完整性和哈希审计，不从图片或 SVG 推导写作规则，也不加载到运行时。 |
| `assets/rednote-zh.svg` | 视觉资产 | `935e4c7d9c2606a6...` | 仅资产 | `docs/maintainers/upstream-adoption-audit.zh.md` | 仅作资产完整性和哈希审计，不从图片或 SVG 推导写作规则，也不加载到运行时。 |
| `assets/x-en.png` | 视觉资产 | `016424a96666490e...` | 仅资产 | `docs/maintainers/upstream-adoption-audit.zh.md` | 仅作资产完整性和哈希审计，不从图片或 SVG 推导写作规则，也不加载到运行时。 |
| `assets/x-en.svg` | 视觉资产 | `7b699c6b14a6be52...` | 仅资产 | `docs/maintainers/upstream-adoption-audit.zh.md` | 仅作资产完整性和哈希审计，不从图片或 SVG 推导写作规则，也不加载到运行时。 |
| `examples/before-after.md` | 示例与回归依据 | `60e73dfa2bab7439...` | 化用 | `plugins/deepscientist-lite/references/communication/academic-writing.md`<br>`tools/validation/prepare_codex_acceptance.py` | 用于设计原创固定回归案例；示例原文不进入运行时输出。 |

## `ai-zixun/humanizer-zh@f75f1ac9`

| 源文件 | 用途 | SHA-256 | 结论 | 本地落点 | 逐文件说明 |
| --- | --- | --- | --- | --- | --- |
| `.claude-plugin/plugin.json` | 仓库元数据或维护配置 | `b23fad0bf38edabf...` | 仅元数据 | `docs/maintainers/upstream-adoption-audit.zh.md` | 仅用于来源、版本、构建或分发审计；不转化为运行时表达规则。 |
| `.github/workflows/release.yml` | 仓库元数据或维护配置 | `069a935894cbb2ff...` | 仅元数据 | `docs/maintainers/upstream-adoption-audit.zh.md` | 仅用于来源、版本、构建或分发审计；不转化为运行时表达规则。 |
| `.gitignore` | 仓库元数据或维护配置 | `9a5362d02d391f20...` | 仅元数据 | `docs/maintainers/upstream-adoption-audit.zh.md` | 仅用于来源、版本、构建或分发审计；不转化为运行时表达规则。 |
| `CHANGELOG.md` | 用户或版本文档 | `afedacc97cdd3983...` | 仅元数据 | `docs/maintainers/upstream-adoption-audit.zh.md` | 仅用于来源、版本、构建或分发审计；不转化为运行时表达规则。 |
| `CLAUDE.md` | 仓库元数据或维护配置 | `c8d65b95534869c6...` | 化用 | `plugins/deepscientist-lite/references/communication/core.md`<br>`plugins/deepscientist-lite/assets/templates/STYLE.md` | 化用项目规则优先级和引号偏好；不复制 Claude 专用配置。 |
| `LICENSE` | 许可证 | `609132fb364baa76...` | 仅许可证 | `plugins/deepscientist-lite/THIRD_PARTY_NOTICES.md`<br>`NOTICE` | 逐字保留许可证和版权声明，并用文件哈希验证；不把许可证改写成通用模板。 |
| `README.en.md` | 用户或版本文档 | `ffc44ca33c6d87b2...` | 仅元数据 | `docs/maintainers/upstream-adoption-audit.zh.md` | 仅用于来源、版本、构建或分发审计；不转化为运行时表达规则。 |
| `README.md` | 用户或版本文档 | `7fdde2bc15316b84...` | 仅元数据 | `docs/maintainers/upstream-adoption-audit.zh.md` | 仅用于来源、版本、构建或分发审计；不转化为运行时表达规则。 |
| `SKILL.md` | 运行时规则入口 | `d7ef1115ef9f0569...` | 化用 | `plugins/deepscientist-lite/references/communication/humanizer-zh.md`<br>`plugins/deepscientist-lite/references/communication/self-audit.md` | 化用文本类型、改写力度、全文主线、保真和朗读复查，重写为科研沟通规则。 |
| `VERSION` | 仓库元数据或维护配置 | `64d23f858ef51b0f...` | 仅元数据 | `docs/maintainers/upstream-adoption-audit.zh.md` | 仅用于来源、版本、构建或分发审计；不转化为运行时表达规则。 |
| `agents/openai.yaml` | 仓库元数据或维护配置 | `1e24f08c08b6c299...` | 仅元数据 | `docs/maintainers/upstream-adoption-audit.zh.md` | 仅用于来源、版本、构建或分发审计；不转化为运行时表达规则。 |
| `references/corpus-quickpick.md` | 深度写作参考 | `b96642965981e96d...` | 化用 | `plugins/deepscientist-lite/references/communication/humanizer-zh.md`<br>`plugins/deepscientist-lite/references/communication/profiles.md` | 化用按文体选择节奏和结构的办法；删除作者名单和模仿入口。 |
| `references/corpus.md` | 深度写作参考 | `bc413788f8afbd05...` | 化用 | `plugins/deepscientist-lite/references/communication/humanizer-zh.md`<br>`plugins/deepscientist-lite/references/communication/profiles.md` | 化用按文体选择节奏和结构的办法；删除作者名单和模仿入口。 |
| `references/patterns.md` | 深度写作参考 | `d65f714ea6f160cf...` | 化用 | `plugins/deepscientist-lite/references/communication/humanizer-zh.md` | 十三类中文模式全部进入本地规则索引，并增加证据、术语和结构化内容保护。 |
| `references/voices/fengtang.md` | 具名作者声音档案 | `b7c2f0cfb564a10d...` | 拒绝运行时采用 | `plugins/deepscientist-lite/references/communication/profiles.md`<br>`plugins/deepscientist-lite/references/communication/core.md` | 已审读并保留快照，但拒绝具名作者人格、口癖和仿写指令；只化用可泛化的结构观察。 |
| `references/voices/hefan.md` | 具名作者声音档案 | `f9d0532de5ef5b4f...` | 拒绝运行时采用 | `plugins/deepscientist-lite/references/communication/profiles.md`<br>`plugins/deepscientist-lite/references/communication/core.md` | 已审读并保留快照，但拒绝具名作者人格、口癖和仿写指令；只化用可泛化的结构观察。 |
| `references/voices/helaoshi.md` | 具名作者声音档案 | `fbb169d2f0fedb1a...` | 拒绝运行时采用 | `plugins/deepscientist-lite/references/communication/profiles.md`<br>`plugins/deepscientist-lite/references/communication/core.md` | 已审读并保留快照，但拒绝具名作者人格、口癖和仿写指令；只化用可泛化的结构观察。 |
| `references/voices/index.md` | 具名作者声音档案 | `149a5314b76bf1ed...` | 拒绝运行时采用 | `plugins/deepscientist-lite/references/communication/profiles.md`<br>`plugins/deepscientist-lite/references/communication/core.md` | 已审读并保留快照，但拒绝具名作者人格、口癖和仿写指令；只化用可泛化的结构观察。 |
| `references/voices/lishanglong.md` | 具名作者声音档案 | `4a5b64649c63be4f...` | 拒绝运行时采用 | `plugins/deepscientist-lite/references/communication/profiles.md`<br>`plugins/deepscientist-lite/references/communication/core.md` | 已审读并保留快照，但拒绝具名作者人格、口癖和仿写指令；只化用可泛化的结构观察。 |
| `references/voices/liuzichao.md` | 具名作者声音档案 | `375f8f104c2e8c2a...` | 拒绝运行时采用 | `plugins/deepscientist-lite/references/communication/profiles.md`<br>`plugins/deepscientist-lite/references/communication/core.md` | 已审读并保留快照，但拒绝具名作者人格、口癖和仿写指令；只化用可泛化的结构观察。 |
| `references/voices/lixiaolai.md` | 具名作者声音档案 | `ff516c95f6eec460...` | 拒绝运行时采用 | `plugins/deepscientist-lite/references/communication/profiles.md`<br>`plugins/deepscientist-lite/references/communication/core.md` | 已审读并保留快照，但拒绝具名作者人格、口癖和仿写指令；只化用可泛化的结构观察。 |
| `references/voices/luozhenyu.md` | 具名作者声音档案 | `69795cf2abf05c5d...` | 拒绝运行时采用 | `plugins/deepscientist-lite/references/communication/profiles.md`<br>`plugins/deepscientist-lite/references/communication/core.md` | 已审读并保留快照，但拒绝具名作者人格、口癖和仿写指令；只化用可泛化的结构观察。 |
| `references/voices/wujun.md` | 具名作者声音档案 | `8a5951493e10d583...` | 拒绝运行时采用 | `plugins/deepscientist-lite/references/communication/profiles.md`<br>`plugins/deepscientist-lite/references/communication/core.md` | 已审读并保留快照，但拒绝具名作者人格、口癖和仿写指令；只化用可泛化的结构观察。 |

## `blader/humanizer@1b485648`

| 源文件 | 用途 | SHA-256 | 结论 | 本地落点 | 逐文件说明 |
| --- | --- | --- | --- | --- | --- |
| `.claude-plugin/marketplace.json` | 仓库元数据或维护配置 | `141736822a343ca0...` | 仅元数据 | `docs/maintainers/upstream-adoption-audit.zh.md` | 仅用于来源、版本、构建或分发审计；不转化为运行时表达规则。 |
| `.claude-plugin/plugin.json` | 仓库元数据或维护配置 | `4d0663f4f41e0519...` | 仅元数据 | `docs/maintainers/upstream-adoption-audit.zh.md` | 仅用于来源、版本、构建或分发审计；不转化为运行时表达规则。 |
| `AGENTS.md` | 仓库元数据或维护配置 | `703873b933df4b07...` | 化用 | `plugins/deepscientist-lite/references/communication/self-audit.md`<br>`tools/validation/validate_repo.py` | 化用源文件与用户文档同步的维护纪律，并交给确定性验证器检查。 |
| `LICENSE` | 许可证 | `4ac4810254ab36d4...` | 仅许可证 | `plugins/deepscientist-lite/THIRD_PARTY_NOTICES.md`<br>`NOTICE` | 逐字保留许可证和版权声明，并用文件哈希验证；不把许可证改写成通用模板。 |
| `README.md` | 用户或版本文档 | `9c24e6b51459d3dc...` | 化用 | `plugins/deepscientist-lite/references/communication/humanizer-en.md`<br>`docs/maintainers/upstream-adoption-audit.zh.md` | 用于核对模式数量、名称和维护同步，不把 README 当运行时入口。 |
| `SKILL.md` | 运行时规则入口 | `243aecdafecb5e11...` | 化用 | `plugins/deepscientist-lite/references/communication/humanizer-en.md`<br>`plugins/deepscientist-lite/references/communication/self-audit.md` | 完整映射 33 类英文模式、误报保护和 draft-audit-final 流程。 |

## 本地生成文件反向映射

| 本地文件 | 来源类型 | 规则编号 | 说明 |
| --- | --- | --- | --- |
| `plugins/deepscientist-lite/references/communication/core.md` | `mixed` | `STYLE-PRECEDENCE`, `EIGHT-HONORS`, `CLAIM-SUPPORT` | Generated or adapted from the explicitly mapped fixed upstream sources. |
| `plugins/deepscientist-lite/references/communication/profiles.md` | `mixed` | `PROFILE-FOUR`, `REJECT-NAMED-AUTHOR-IMITATION` | Generated or adapted from the explicitly mapped fixed upstream sources. |
| `plugins/deepscientist-lite/references/communication/self-audit.md` | `mixed` | `START-ACTION-HANDOFF`, `SOURCE-GENERATED-SYNC` | Generated or adapted from the explicitly mapped fixed upstream sources. |
| `plugins/deepscientist-lite/references/communication/humanizer-zh.md` | `adapted` | `ZH-WORKFLOW`, `ZH-PATTERN-01-13` | Generated or adapted from the explicitly mapped fixed upstream sources. |
| `plugins/deepscientist-lite/references/communication/humanizer-en.md` | `adapted` | `EN-PATTERN-01-33`, `EN-DRAFT-AUDIT-FINAL` | Generated or adapted from the explicitly mapped fixed upstream sources. |
| `plugins/deepscientist-lite/references/communication/academic-writing.md` | `adapted` | `ACADEMIC-LAYER-01-06`, `CLAIM-EVIDENCE`, `CLAIM-FEASIBILITY` | Generated or adapted from the explicitly mapped fixed upstream sources. |
| `plugins/deepscientist-lite/references/communication/upstream-adoption.json` | `generated` | `UPSTREAM-INVENTORY`, `NINE-FIELD-MATRIX` | Generated or adapted from the explicitly mapped fixed upstream sources. |
| `plugins/deepscientist-lite/references/communication/upstream/_manifests/source-files.json` | `generated` | `SOURCE-SNAPSHOT-HASH` | Generated or adapted from the explicitly mapped fixed upstream sources. |
| `plugins/deepscientist-lite/assets/templates/STYLE.md` | `project-native` | `PROFILE-CONFIG` | Original DeepScientist Lite contract or deterministic enforcement code. |
| `plugins/deepscientist-lite/scripts/ds_lite_communication_audit.py` | `project-native` | `COMMUNICATION-AUDIT-V1` | Original DeepScientist Lite contract or deterministic enforcement code. |
| `plugins/deepscientist-lite/scripts/ds_lite_hook.py` | `project-native` | `HOOK-FOUR-EVENTS`, `CLAIM-GATE` | Original DeepScientist Lite contract or deterministic enforcement code. |
| `plugins/deepscientist-lite/hooks/hooks.json` | `project-native` | `HOOK-ADAPTER` | Original DeepScientist Lite contract or deterministic enforcement code. |
| `plugins/deepscientist-lite/THIRD_PARTY_NOTICES.md` | `generated` | `LICENSE-EXACT` | Generated or adapted from the explicitly mapped fixed upstream sources. |
| `tests/test_communication_layer.py` | `project-native` | `COMMUNICATION-REFERENCE-TEST` | Original DeepScientist Lite contract or deterministic enforcement code. |
| `tests/test_communication_audit.py` | `project-native` | `COMMUNICATION-AUDIT-TEST` | Original DeepScientist Lite contract or deterministic enforcement code. |
| `tests/test_communication_hook.py` | `project-native` | `HOOK-BEHAVIOR-TEST` | Original DeepScientist Lite contract or deterministic enforcement code. |
| `tests/test_upstream_adoption.py` | `project-native` | `UPSTREAM-AUDIT-TEST` | Original DeepScientist Lite contract or deterministic enforcement code. |
| `docs/maintainers/upstream-adoption-audit.zh.md` | `generated` | `UPSTREAM-INVENTORY` | Generated or adapted from the explicitly mapped fixed upstream sources. |

## 明确不采用

- 不启用任何具名作者 persona，不复制作者口癖，不提供作者模仿 profile。
- 不把上游 skill、Claude 插件清单、marketplace 或发布流程变成 DS Lite 运行时依赖。
- 不把视觉资产解释成文本规则，不从示例补造科研数据、引用、合作方或实验结果。
- 不使用 humanizer 掩盖 AI 辅助披露义务，也不把表达改写当成证据验证。

## 复核命令

```bash
python tools/validation/audit_upstream_adoption.py
```
