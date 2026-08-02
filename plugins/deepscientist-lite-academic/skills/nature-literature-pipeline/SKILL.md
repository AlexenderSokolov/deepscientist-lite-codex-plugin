---
name: nature-literature-pipeline
description: Use the complete nature-literature-pipeline workflow, preserving its upstream routing and supporting materials. | Complete automated literature discovery pipeline; multi-source search → six-dimension scoring → fine reading → formatted delivery → archival. Combines a configurable engine with daily cron-driven application layer. Works with Feishu, Telegram, or any messaging platform.
---

# DS Lite Integration Boundary

This entry preserves the complete upstream nature-literature-pipeline workflow at commit `91862221b39f7ca16d52ae0e1e9cb6c2bb31a96b`.
Use the upstream manifest, static fragments, references, scripts, templates, and tests
that remain in this directory; this file is not a summary replacement.

Before using any MCP, external API, browser, downloader, LaTeX, Node, or Python
integration, first run `python <academic-plugin>/scripts/ds_lite_pack_doctor.py --core-root <core-plugin>`, then run
`python <academic-plugin>/scripts/ds_lite_nature_setup.py doctor --workspace .`.
Record only redacted status and relative evidence references. Missing dependencies are
`not-observed` or `blocked`, never silently treated as available.

Read [responsible-exploration-covenant.md](../../references/responsible-exploration-covenant.md) first.
Every invocation follows DS Lite `start / progress / end`: state the target, facts,
authorization, actual action, evidence, failure layer, unverified items, and one next
action. Do not save prompts, credentials, raw responses, hidden reasoning, or absolute
workstation paths.

## Preserved Upstream Workflow

# Nature Literature Pipeline

A complete, production-tested automated literature pipeline. Not just "search for papers" — it's a structured engine that scores, classifies, reads, delivers, and archives research papers daily.

## What It Does

```
Cron (daily trigger, e.g. 08:30)
  │
  ├─ ① SEARCH (30 candidates)
  │   arXiv / OpenAlex / Crossref / Semantic Scholar (auto-degradation)
  │
  ├─ ② COARSE FILTER (30 → 5)
  │   Six-dimension scoring: topic match × 35 + methodology × 20
  │   + journal quality × 15 + network relevance × 10
  │   + applied value × 10 + archival value × 10
  │
  ├─ ③ FINE READ (top 5)
  │   Abstract-level or full-text. Source level tagged:
  │   Full-text / Abstract only / Metadata only
  │
  ├─ ④ DELIVER
  │   Formatted digest to Feishu/Telegram/etc.
  │   🏅 rank | title | journal | ⭐ score | 💡 one-liner
  │   🔬 methods | 📊 key results | 🧭 commentary
  │
  └─ ⑤ ARCHIVE
      DOI/arXiv de-dup → classify → write notes → update index
```

## Quick Start

After installing, tell your agent:

```
My research area is [X], keywords: [Y], deliver to [feishu group name], archive to [path]
```

The agent will configure keywords, delivery target, and archive path automatically.

Then set up a daily cron job:

```
Set up a daily literature push at 08:30 Beijing time, 30 candidates, top 5 delivered
```

## Architecture

The skill is organized in two layers:

| Layer | Purpose | Files |
|-------|---------|-------|
| **Engine** | Scoring, classification, note templates, gap analysis | `references/scoring-system.md`, `references/gap-analysis.md`, `references/note-template.md` |
| **Application** | Daily cron pipeline, delivery formatting, archival workflow | `references/push-format.md`, `references/cron-setup.md`, `references/review-compilation-workflow.md` |

## Configuration

All domain-specific content is configurable:

- **Keywords** — your research keywords (English + Chinese)
- **Scoring weights** — adjust the six dimensions for your field
- **Classification rules** — define your own tier system (A-E or custom)
- **Delivery target** — Feishu group, Telegram channel, email, etc.
- **Archive path** — local vault/wiki directory

A config template is provided in `templates/literature-push-template.md`.

## Built-in Safeguards

- **Score validation**: Each dimension capped, total recalculated — no 11/10 allowed
- **Triple de-duplication**: DOI / arXiv ID / OpenAlex ID
- **Graceful degradation**: Semantic Scholar down → auto-switch to OpenAlex + Crossref + arXiv
- **Read-only archive**: Daily pipeline writes to `raw/` literature directory only; never modifies wiki/knowledge base without user approval

## Related Skills

- `nature-academic-search` — ad-hoc literature search (complementary; this skill adds structured daily automation)
- `nature-citation` — CNS citation export (for importing pipeline discoveries into manuscripts)
- `zotero` — library management (for long-term organization of pipeline outputs)
- `arxiv` — arXiv API (used as a search source)

## References

| Reference | Purpose |
|-----------|---------|
| `references/scoring-system.md` | Six-dimension scoring rubric with weights, caps, and evaluation logic |
| `references/gap-analysis.md` | Methodology for identifying research gaps through systematic literature survey |
| `references/note-template.md` | Standardized literature note format with YAML frontmatter |
| `references/push-format.md` | Daily digest message template with field guidelines and example |
| `references/cron-setup.md` | Cron job creation, verification, and manual fallback procedures |
| `references/review-compilation-workflow.md` | End-to-end workflow for concentrated literature review writing |

## Pitfalls

1. **Keyword drift**: Review keywords monthly — research directions evolve
2. **Score inflation**: Subagents may inflate scores; always validate arithmetic
3. **Duplicate creep**: Classic papers will reappear; maintain a dedup index
4. **Wiki safety**: Pipeline writes to `raw/` only; wiki integration is manual
5. **Cron locality**: Hermes cron is local, not cloud — machine must be running
