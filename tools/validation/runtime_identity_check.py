"""Reject new active-runtime Codex version literals outside identity helpers."""
from __future__ import annotations

import re
from pathlib import Path


ACTIVE_FILES = (
    "plugins/deepscientist-lite-core/controller/ds_lite_control/cli.py",
    "plugins/deepscientist-lite-core/controller/ds_lite_control/dbos_bridge.py",
    "teaching/formal_cache_acceptance.py",
    "teaching/pilot_runtime.py",
    "teaching/matched_blind_reviewer.py",
    "teaching/fresh_runtime_candidate_acceptance.py",
    "tools/validation/phase5_host_candidate_acceptance.py",
    "tools/validation/phase5_candidate_revalidation.py",
)

FORBIDDEN = (
    re.compile(r"(?:CODEX_VERSION|STABLE_CODEX_VERSION|PHASE5_CODEX_VERSION)\s*=\s*['\"]\d+\.\d+\.\d+"),
    re.compile(r"(?:EXPECTED_CODEX_VERSION|EXPECTED_VERSION|PINNED_CLI_VERSION)\s*=\s*['\"]\d+\.\d+\.\d+"),
    re.compile(r"codex_version\s*:\s*str\s*=\s*['\"]\d+\.\d+\.\d+"),
)


def check_runtime_identity(repo_root: Path) -> list[str]:
    issues: list[str] = []
    for relative in ACTIVE_FILES:
        path = repo_root / relative
        if not path.is_file():
            issues.append(f"missing:{relative}")
            continue
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if any(pattern.search(line) for pattern in FORBIDDEN):
                issues.append(f"hardcoded-version:{relative}:{line_number}")
    return issues


__all__ = ["check_runtime_identity"]
