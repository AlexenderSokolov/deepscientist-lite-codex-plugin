# Communication Self-Audit

Use this contract for every DS Lite skill. Scale the prose to the task, but do
not skip an applicable check. Record only observable facts and concise reasons;
never record hidden reasoning or chain-of-thought.

## Phase 1: before action

1. **Outcome**: state the requested result and the acceptance condition.
2. **Evidence already available**: list the governing project files, user
   statements, schemas, source documents, or observed state.
3. **Unknowns**: separate missing facts from preferences and permissions.
4. **Reuse**: name the existing helper, template, runner, schema, or local
   pattern that will be reused. If none exists, say what was searched.
5. **Risk and boundary**: identify protected content, irreversible actions,
   scope exclusions, and the stop condition.
6. **Plan visibility**: for a non-trivial task, tell the user what will be
   inspected, changed, and verified before editing.

The phase fails when work begins from an undefined goal, an assumed interface,
an invented business rule, or unconfirmed destructive authorization.

## Phase 2: after each action

Record what actually happened, not what the action was intended to do:

- inspected paths and source versions;
- changed or created project-relative paths;
- command, exit status, and high-signal result;
- warnings, stderr, incomplete output, and negative results;
- unexpected user changes encountered and how they were preserved;
- which hypothesis, expectation, or plan changed because of the result.

Do not smooth a failed command into progress. A failed attempt may be useful
evidence, but it remains failed until another observed result supersedes it.

## Phase 3: before handoff

The handoff must answer every applicable item:

1. **Result**: what is now true, using claim strength supported by evidence.
2. **Actions**: what was read, created, changed, run, or deliberately left alone.
3. **Evidence**: project-relative paths, source commits, commands, hashes, or
   validation results that support the result.
4. **Verification**: exact checks that ran and their outcomes.
5. **Limitations**: unrun checks, unsupported host behavior, unresolved errors,
   partial coverage, and scientific uncertainty.
6. **Reflection**: expectation gap, negative result, falsifiability, possible
   bias, and what failure would change when these are material.
7. **Next step**: the smallest defensible action and who owns any decision or
   authorization.

For a blocked task, replace a success summary with blocker, attempted evidence,
why the task cannot continue, and the exact user decision or access needed.

## Task-class minimums

| Task class | Minimum semantic content |
| --- | --- |
| Settled answer | Answer, basis or scope, and uncertainty if any. |
| Repository change | Goal, inspected files, changed files, verification, limitations, next step. |
| Diagnosis | Symptom, system boundary, evidence, root cause or hypotheses, discriminator, next check. |
| Blocked execution | Blocker, attempts, evidence, safe stopping state, required decision. |
| Academic rewrite | Cleaned text, change report, claim/evidence changes, protected-content confirmation. |
| Methodological reflection | Assumptions, falsifiability, bias, uncertainty, failure meaning, next test. |

## Completion-claim checklist

Before using `read`, `changed`, `tested`, `verified`, `fixed`, or `completed`,
bind the claim to evidence. If the evidence is missing, choose one:

- obtain the evidence;
- say `not verified`;
- say `planned`;
- report the task as `blocked`.

Never use confident wording to compensate for an absent source, test, or
artifact. Never count the existence of this checklist as proof it was followed.

## Protected output

Compare protected strings before and after narrative rewriting. Numbers, units,
formulas, citation keys, commands, paths, schema keys, JSON/YAML, logs, metrics,
quoted text, and formal definitions must remain unchanged unless the task
explicitly authorizes a source correction. A changed protected string is a hard
failure, not a style preference.
