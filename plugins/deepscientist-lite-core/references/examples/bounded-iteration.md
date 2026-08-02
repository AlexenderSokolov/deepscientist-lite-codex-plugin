# Bounded iteration example

## Input

A baseline run exists, but its metric file has not passed Evidence Pack
verification. The user asks to continue improving the model.

## Decision

Do not start a new experiment. Open one iteration whose action is to validate
the existing pack and classify the failure layer. The evidence gate owns the
route; a new score would only add ambiguity.

## Artifact

Write the running iteration receipt, validation output, failure classification,
and one next action. Keep every path project-relative.

## Failure and rollback

If a hash mismatch appears, close the iteration as `blocked`, preserve the
pack, and return to the last reviewed node. Do not repair or overwrite the
artifact in place. A supervisor may authorize a new run with a new run ID.

