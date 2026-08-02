# Evaluation layer

This directory is the stable index for non-runtime evaluation assets. During
the compatibility period, deterministic runners, fixtures, and score tools
remain under `teaching/`; they are not copied into an installable plugin and
are not treated as user-facing product documentation.

- `teaching/lab_runner.py`: deterministic protocol fixtures.
- `teaching/pilot_runtime.py`: preregistered 4-case x 3-arm execution harness.
- `teaching/pilot_score.py`: public-artifact scoring and blind-review input.
- `teaching/explainability_score.py`: disaggregated explainability measures.
- `teaching/offline_acceptance.py`: fake-provider/fake-host protocol checks.
- `cross-disciplinary-upstreams.json`: fixed commit/license/hash records and clean-room design-atom decisions for the 2026-07-24 academic, empirical, and engineering expansion.
- `plugins/*/references/`: small, on-demand agent examples and decision rules.

The package validator covers six deterministic matrices: `core-only`,
`core+academic`, `core+empirical`, `core+engineering`,
`core+web+knowledge`, and `all-six`. These matrices prove source boundaries
only; they do not unlock real provider, Hook, delegation, matched-effect,
formal-cache, fresh-Desktop, or release gates.

Migration is index-first. Old files stay in place until a separately approved
cleanup; no source or evidence identity is rewritten by moving files.
