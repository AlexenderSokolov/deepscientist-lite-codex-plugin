# Package Layout

This repository is a Codex marketplace repository.

## Runtime Plugin Packages

- `.agents/plugins/marketplace.json`: one marketplace exposing six independently installable packages.
- `plugins/deepscientist-lite-core/`: `deepscientist-lite` `0.9.0-beta.1`; nine Core skills, Graph/Evidence/iteration/delegation/handoff scripts, templates, learning/quality gates, Hooks, and the bounded foreground autonomy controller. The package has no vendor snapshot, MCP server, daemon, database, or browser runtime.
- `plugins/deepscientist-lite-academic/`: `0.9.0-beta.1`; the 17 adapted Nature skills plus citation, revision, and adversarial-review protocols. It checks for the matching Core and owns no Hook.
- `plugins/deepscientist-lite-web/`: `0.3.0-alpha.1`; public-only capability and v1/v2 source-record protocols plus bounded HTTP provenance recording. Playwright, Firecrawl, Tapestry, and agent-browser remain optional external backends.
- `plugins/deepscientist-lite-knowledge/`: `0.3.0-alpha.1`; review-gated Tapestry and ScholarAIO handoffs. It does not own either upstream store or write formal ResearchKB knowledge directly.
- `plugins/deepscientist-lite-empirical/`: `0.3.0-alpha.1`; one method-neutral router for empirical specs, diagnostics, robustness, and Core Evidence Pack results.
- `plugins/deepscientist-lite-engineering/`: `0.3.0-alpha.1`; one router for numerical, FFT, sampling, simulation, units, and figure checks.
- `plugins/deepscientist-lite/`: frozen `0.6.0-beta.1` monolith retained only for evidence identity and compatibility during the transition. It is no longer the marketplace target.

Each optional package publishes `compatibility.json` and fails closed unless it observes `deepscientist-lite` `0.9.0-beta.1`. Marketplace dependency propagation is not assumed.

## Core Runtime Files

- `plugins/deepscientist-lite-core/scripts/ds_lite_state.py`: no-dependency state graph helper.
- `plugins/deepscientist-lite-core/scripts/ds_lite_evidence.py`: no-dependency Evidence Pack contract, finalize, and verification helper.
- `plugins/deepscientist-lite-core/scripts/ds_lite_protocol.py`: strict work-unit, review-result, Factor Card, and bounded-delegation validator.
- `plugins/deepscientist-lite-core/scripts/ds_lite_iteration.py`: strict init/finalize/verify helper for one reflective iteration; not an exactly-once transaction.
- `plugins/deepscientist-lite-core/scripts/ds_lite_hook.py` and `hooks/hooks.json`: stateless, redacted Hook helper and candidate host configuration; split-package fresh-host loading is not verified.
- `plugins/deepscientist-lite-core/scripts/ds_lite_loop.py`: bounded loop adapter with fail-closed external execution boundaries.
- `plugins/deepscientist-lite-core/scripts/ds_lite_autonomy.py`: foreground DAG controller for frozen, authorized gates, bounded transient retries, and sanitized progress receipts.
- `plugins/deepscientist-lite-academic/scripts/ds_lite_nature_setup.py`: package-local inventory, onboarding, and workspace configuration checks.
- `plugins/deepscientist-lite-core/assets/templates/`: project file templates.
- `plugins/deepscientist-lite-core/references/`: Core protocol references only.

## Non-Runtime Material

- `docs/`: implementation and maintainer documentation.
- `teaching/`: standalone courses, the standard-library lab runner, cross-platform wrappers, worksheets, and sanitized fixtures; none are loaded as plugin runtime.
- `tools/validation/`: maintainer validation tools.
- `tools/validation/upstream_manager.py`: read-only upstream inventory, provenance check, diff observation, and update-plan generator.
- `tests/`: standard-library Graph v2, Evidence Pack, and CLI regression tests.
- `.github/workflows/validate.yml`: Windows and Ubuntu validation matrix.

## Release Boundary

Core remains lightweight: no MCP server, daemon, Web/TUI, connector, local model bundle, academic snapshot, or web backend is declared in its manifest. Optional packages do not acquire global state or bypass Core approval and stopping rules.

Run the package-specific wrappers under `tools/validation/runners/` (`run_validate_core.*`, `run_validate_academic.*`, `run_validate_web.*`, `run_validate_knowledge.*`, `run_validate_empirical.*`, and `run_validate_engineering.*`). `tools/validation/validate_packages.py --package all` checks eight install matrices, route collisions, compatibility contracts, package digests, and Core/domain size limits. It deliberately reports real Hook, delegation, matched effect, formal cache, fresh Desktop, and release gates as `not-verified`.

## Skills Aggregation Plan

The Academic package currently exposes 17 skills. The following aggregation is planned to reduce entry-point count while preserving all functionality:

| Original skills | Aggregated skill | Strategy |
| --- | --- | --- |
| `nature-academic-search` + `nature-citation` + `nature-ref-verifier` | `nature-literature` | Router with search, citation, and ref-verifier sub-routes |
| `nature-reader` + `nature-downloader` | `nature-reader` | Downloader as reader's pre-step |
| `nature-writing` + `nature-polishing` | `nature-writing` | Router with drafting and polishing sub-routes |
| `nature-reviewer` + `nature-response` | `nature-review` | Router with reviewer and response sub-routes |
| `nature-paper2ppt` + `nature-paper-to-patent` | `nature-convert` | Router with paper2ppt and paper-to-patent sub-routes |

After aggregation, the Academic package will expose approximately 11 skills instead of 17. The original skills remain available as sub-routes within the aggregated entry points.

## Public/Private File Boundary

The following files are marked as private and excluded from public release:

- `docs/maintainers/`: internal maintainer documentation, not for public release.
- `PROJECT.md`: local project context, not for public release.
- `evaluation/`: private evaluation data.

These are configured in `.gitignore` to prevent accidental publication.
