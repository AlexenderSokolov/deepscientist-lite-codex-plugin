# Empirical protocol

`ds-lite.empirical-spec.v1` is the preregistered method contract. It separates the estimand and identifying assumptions from the language or statistics package used to estimate it. Data references remain project-relative; the pack never downloads or stores a dataset by itself.

`ds-lite.empirical-result.v1` is the result handoff. It preserves every planned diagnostic and robustness outcome, including failures, disagreement, and null results. Its `evidence_pack_ref` points to the Core Evidence Pack; ordinary artifact paths do not become evidence merely because they exist.

The reference backend is Python when observed. R, Stata, and StatsPAI are capability-discovered and optional. `not-observed` means the environment was not proven, not that the method is unsupported.
