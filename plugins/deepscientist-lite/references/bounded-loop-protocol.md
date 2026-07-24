# Bounded Loop Protocol

`ds-lite.loop-contract.v1` lets an approved foreground supervisor advance
several independent `$ds-lite-iterate` cycles without changing the rule that
one iterate invocation performs exactly one bounded action.

## Autonomy boundary

Continue autonomously through harmless, reversible, authorized work when the
previous round is terminal, verified, and classified `partial` with
`failure_layer=none`. Continue independent read-only analysis and offline
validation when another branch is blocked. Do not ask the user to run ordinary
repository commands that the current execution surface can run safely.

Stop before deletion, publication, credential or formal-cache changes, new
external requests, resource expansion, or any irreversible action unless the
contract already carries explicit authority. Stop immediately on `blocked`,
`failed`, `ambiguous`, `timeout`, `auth`, `rate-limit`, `network`, `protocol`,
or `duplicate-risk`.

## Contract and receipts

The contract freezes goal ids and required project-relative evidence refs. The
working plan and prompt remain referenced files and are not copied into the
contract. Budgets require a bounded round count and wall-clock limit. Existing
contracts and receipts are never overwritten.

Each round receipt stores only a session hash, completion-signal observation,
completed goal ids, missing evidence, continuation decision, failure layer,
and one next action. It never stores raw JSONL, stdout/stderr, a prompt, hidden
reasoning, credentials, URLs, environment dumps, or workstation roots.

Completion requires all three gates:

1. A structured completion signal is observed.
2. Every frozen goal id is reported complete and every evidence ref exists.
3. The loop summary passes verification and the surrounding acceptance gate.

A natural-language claim of completion is not a completion signal. A
continuation is not a retry: only a clean nonterminal iteration may continue.

## Adapters

- `fake` is deterministic and is the only adapter used by offline acceptance.
- `native-codex` invokes a foreground Codex CLI process and requires both an
  approved contract and the explicit `--execute` flag.
- `codex-autoresearch` is an `adopted / adapted` compatibility adapter backed by
  the authorized fixed vendor snapshot. The current upstream CLI writes raw
  event and runner logs and does not yet expose the sanitized child-output
  contract required by DS Lite. Its execution state remains
  `blocked-not-verified`: `codex_autoresearch_adapter.py` can inspect the
  version, license, source and tests, but refuses to spawn and returns
  `external-policy-unverified` until a redacted child contract is supplied;
  it does not execute the external CLI in this state.

No adapter creates a daemon, queue, scheduler, database, MCP service, tmux
capacity, or background process.

`allowed_paths` is an evidence allowlist used by the completion gate. It is not
an operating-system write sandbox. Round receipts provide fresh-only state and
consistency checks; they are not a signed hash chain, an exactly-once journal,
or proof that a real Codex continuation has run. Fake acceptance proves only
the supervisor protocol.
