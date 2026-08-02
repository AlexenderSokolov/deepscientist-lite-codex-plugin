# Knowledge adapter boundary

This pack does not own a paper library or a formal knowledge base. It accepts
review-safe handoff envelopes and emits pending `ds-lite.knowledge-proposal.v1`
records. Outputs must live in a user project or explicit external root, never
in the installed plugin.

## Tapestry

The experimental `ds-lite.tapestry-handoff.v1` envelope contains `items` with
an ID, title, summary, source-record references, and optional claims. Capture,
feed, and note data remain owned by Tapestry or the user project. Alpha output
cannot bypass review.

## ScholarAIO

The `ds-lite.scholaraio-handoff.v1` envelope contains `papers` with the same
review-safe fields. ScholarAIO continues to own import, parsing, collections,
search, and reading. DS Lite stores references, not a duplicate paper object.

Run `ds_lite_knowledge.py adapt-tapestry` or `adapt-scholaraio` to create a
fresh pending proposal batch. Promotion, rejection, withdrawal, supersession,
and deduplication are target-native review actions.

