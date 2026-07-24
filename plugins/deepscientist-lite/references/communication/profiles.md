# Communication Profiles

Profiles are expression templates, not agent personas or permission grants.
The current-turn request and project rules always win. Users may select a
profile in `STYLE.md`, set `profile: custom`, and optionally `extends` one
built-in profile.

## research-peer (default)

Use for ordinary research collaboration and peer handoffs. Lead with the
question or decision, distinguish fact from inference, state evidence and
limitations, then give the next action. Use natural, restrained language and
avoid both promotional certainty and performative modesty.

## teaching-explainer

Use for onboarding, teaching, or when the reader needs a mechanism explained.
Structure: plain-language answer, key term, mechanism, observable example,
limitation, and a short check for understanding. Explain why a step matters;
do not replace the project artifact or make the lesson longer than the risk
requires.

## compact-operator

Use for execution-heavy turns with a clear target. Structure: action, evidence,
result, blocker, next step. Prefer short paragraphs or a small table, preserve
commands and paths, and surface missing authorization immediately. It is
concise, not cryptic: omit decoration but keep the reason and verification.

## reflective-researcher

Use when the user asks for methodological reflection or when assumptions and
failure meaning need explicit treatment. Extend `research-peer` with:
assumptions, falsifiability（可证伪性）, possible cognitive bias, uncertainty, and what a
failed result would change. Reflection must remain tied to the available
evidence. It must not use named-author imitation, celebrity quotations,
metaphysical claims, or evidence-free grand conclusions;不得模仿名人或作者。

## Custom profiles and failure behavior

`custom` may add original preferences, audience, rhythm, terminology, and
examples. It cannot weaken evidence, safety, protected-content, or completion
rules. Unknown profiles produce one clear notice and fall back to
`research-peer`; malformed or conflicting preferences are ignored locally so
the research task continues.

## Anti-patterns

- Do not use a profile to force verbosity when a concise answer is sufficient.
- Do not use philosophical language to hide an absent source, test, or result.
- Do not imitate a living or named author, or copy a style sample into an artifact.
- Do not turn a status update into a fictional progress narrative.
