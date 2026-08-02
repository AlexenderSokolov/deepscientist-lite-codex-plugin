# CLI Boundary Compatibility

Windows PowerShell, `cmd`, Git Bash, WSL/Linux Bash, and an external host are
different execution surfaces. A command that works in one surface is not proof
that quoting, encoding, PATH, process-tree, or pipe behavior matches another.

Before a real request, run a model-free probe for the pinned binary, version,
PATH resolution, working directory, shell surface, UTF-8 mode, provider route,
and retry policy. Keep argv as a count and hash; never persist a prompt, token,
URL, full environment, or raw stdout/stderr. Detect and report:

- quoting or escaping failures (`&`, `|`, `<`, `>`, backticks, `$`, parentheses,
  JSON quotes, and non-ASCII arguments);
- encoding failures and replacement-character output;
- PATH or working-directory mismatches;
- `.cmd` wrapper versus child process exit and pipe closure;
- WSL path translation or shell-boundary failures;
- authentication and timeout observations.

Use `teaching/cli_compatibility.py` for `ds-lite.cli-compatibility.v1`. A
nonzero exit, missing terminal event, open pipe, or zero-event process is a
diagnostic outcome, not a retry instruction. Reproduce a failure only under a
new audited identity and one explicit hypothesis per request.
