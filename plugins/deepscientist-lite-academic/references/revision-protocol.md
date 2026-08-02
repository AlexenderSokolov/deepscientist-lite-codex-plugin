# Revision and adversarial-review protocol

`ds-lite.revision-constraints.v1` bounds a manuscript pass by allowed paths, creation or deletion effects, approvals, files changed, and operation count. New citations, numbers, theorems, citation deletions, and section deletions are separate controls. A permitted semantic operation still requires an approval reference.

Adversarial review emits `ds-lite.adversarial-review.v1` with one strongest rejection argument and atomic P0-P3 concerns. Context isolation is `observed` only when both attack and adjudication receipts explicitly say fresh and use different context IDs; otherwise it is `not-observed`.

The workflow remains one bounded edit/review cycle followed by a checkpoint. It is not an unattended ARIS loop, monitor, experiment queue, or authority to invent data.
