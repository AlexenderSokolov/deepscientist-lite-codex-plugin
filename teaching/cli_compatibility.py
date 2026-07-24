#!/usr/bin/env python3
"""Classify common CLI boundary failures without retaining commands or output."""

from __future__ import annotations

import hashlib
import re
from typing import Iterable


SCHEMA_VERSION = "ds-lite.cli-compatibility.v1"
SHELLS = {"powershell", "windows-powershell", "cmd", "git-bash", "wsl-bash", "linux-bash", "external-host", "unknown"}
FAILURES = {"none", "encoding", "quoting", "path", "wrapper", "pipe", "auth", "protocol", "timeout", "unknown"}
SECRET = re.compile(r"(?i)(sk-[A-Za-z0-9_-]+|bearer\s+\S+|api[_-]?key\s*[=:]\s*\S+)")


def _redact(value: str) -> str:
    return SECRET.sub("<redacted>", value)


def argv_projection(argv: Iterable[str]) -> dict[str, object]:
    values = [_redact(str(item)) for item in argv]
    return {
        "argc": len(values),
        "argv_sha256": hashlib.sha256("\0".join(values).encode("utf-8", "replace")).hexdigest(),
        "shell_metacharacter_observed": any(any(char in item for char in "&|<>^`$()") for item in values),
        "secret_marker_observed": any("<redacted>" in item for item in values),
    }


def classify_lines(lines: Iterable[str], *, shell: str, returncode: int | None,
                   stdout_pipe: str, stderr_pipe: str, timed_out: bool = False) -> dict[str, object]:
    shell_name = shell if shell in SHELLS else "unknown"
    observed_lines = [str(line) for line in lines]
    text = "\n".join(observed_lines)
    lowered = text.lower()
    if timed_out:
        failure = "timeout"
    elif any(token in lowered for token in ("unauthorized", "forbidden", "not logged in", "authentication", "invalid api key", "401", "403")):
        failure = "auth"
    elif any(token in lowered for token in ("not recognized", "command not found", "no such file", "cannot find the path", "path not found")):
        failure = "path"
    elif any(token in lowered for token in ("unexpected token", "unterminated", "missing closing", "quote", "parsing")):
        failure = "quoting"
    elif any(token in lowered for token in ("unicode", "encoding", "decode", "invalid byte", "replacement character")):
        failure = "encoding"
    elif any(token in lowered for token in (".cmd", "cmd.exe", "child process", "wrapper", "arg0", "pipe remains open")):
        failure = "wrapper"
    elif any(token in lowered for token in ("invalid json", "malformed response", "unexpected event", "invalid event", "response.completed", "jsonl", "protocol")):
        failure = "protocol"
    elif "pipe" in lowered or stdout_pipe != "closed" or stderr_pipe != "closed":
        failure = "wrapper"
    elif returncode not in (None, 0):
        failure = "unknown"
    else:
        failure = "none"
    return {
        "schema_version": SCHEMA_VERSION,
        "shell_surface": shell_name,
        "failure_class": failure,
        "returncode_observed": returncode is not None,
        "stdout_pipe_state": stdout_pipe,
        "stderr_pipe_state": stderr_pipe,
        "timeout_observed": timed_out,
        "diagnostic_line_count": len(observed_lines),
        "diagnostic_sha256": hashlib.sha256(text.encode("utf-8", "replace")).hexdigest(),
        "raw_output_persisted": False,
    }
