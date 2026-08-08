"""Small SemVer v2 comparator shared by DS Lite package doctors."""
from __future__ import annotations

import re
from typing import Any


SEMVER_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?$")


class SemVerError(ValueError):
    pass


def parse(value: Any) -> tuple[int, int, int, tuple[tuple[int, int | str], ...]]:
    if not isinstance(value, str):
        raise SemVerError("version must be a SemVer string")
    match = SEMVER_RE.fullmatch(value)
    if not match:
        raise SemVerError(f"invalid SemVer: {value!r}")
    prerelease: list[tuple[int, int | str]] = []
    if match.group(4):
        for part in match.group(4).split("."):
            if part.isdigit():
                if len(part) > 1 and part.startswith("0"):
                    raise SemVerError(f"invalid numeric prerelease identifier: {value!r}")
                prerelease.append((0, int(part)))
            else:
                prerelease.append((1, part))
    return int(match.group(1)), int(match.group(2)), int(match.group(3)), tuple(prerelease)


def compare(left: str, right: str) -> int:
    a, b = parse(left), parse(right)
    if a[:3] != b[:3]:
        return -1 if a[:3] < b[:3] else 1
    if not a[3] or not b[3]:
        return 0 if a[3] == b[3] else (-1 if a[3] else 1)
    for a_part, b_part in zip(a[3], b[3]):
        if a_part == b_part:
            continue
        if a_part[0] != b_part[0]:
            return -1 if a_part[0] == 0 else 1
        return -1 if a_part[1] < b_part[1] else 1
    return 0 if len(a[3]) == len(b[3]) else (-1 if len(a[3]) < len(b[3]) else 1)


def satisfies(version: str, expression: str) -> bool:
    parse(version)
    terms = expression.split()
    if not terms:
        raise SemVerError("compatibility expression is empty")
    for term in terms:
        match = re.fullmatch(r"(>=|<=|>|<|=)?(.+)", term)
        if not match:
            raise SemVerError(f"invalid compatibility term: {term!r}")
        operator, bound = match.groups()
        relation = compare(version, bound)
        checks = {None: relation == 0, "=": relation == 0, ">=": relation >= 0, "<=": relation <= 0, ">": relation > 0, "<": relation < 0}
        if not checks[operator]:
            return False
    return True
