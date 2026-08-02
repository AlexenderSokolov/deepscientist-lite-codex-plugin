# Selective Superpowers Adaptation

DeepScientist Lite selectively adapts open-source engineering disciplines that
improve bounded work:

- check applicable skills before acting;
- write a short plan before mutation;
- use a failing test to define a narrow change;
- keep one bounded action and an explicit stop condition;
- verify actual files and commands before reporting success;
- hand off authority, context, configuration, evidence, and next action
  explicitly.

These are process rules, not a new runtime. DS Lite does not import hidden
reasoning, daemon/queue/scheduler behavior, MCP services, automatic retries,
unbounded loops, or a second approval system. Existing covenant labels,
acceptance gates, delegation limits, and fail-closed status remain authoritative.

Maintainers test three states with `tools/validation/audit_superpowers.py`:
absent, present, and ownership conflict. Presence delegates only the four
process roles above. Any claim that Superpowers owns research state, approval,
evidence, or the stop gate is a conflict and must block.
