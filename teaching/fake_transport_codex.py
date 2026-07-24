#!/usr/bin/env python3
"""Deterministic fake Codex process used only by offline transport acceptance."""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request


SECRET_MARKER = "FAKE-STDERR-SECRET"


def emit(event: dict) -> None:
    print(json.dumps(event, ensure_ascii=True), flush=True)


def main() -> int:
    scenario = os.environ["DS_LITE_FAKE_SCENARIO"]
    if scenario == "child-early-exit":
        return 7

    emit({"type": "thread.started", "thread_id": f"offline-{scenario}"})
    request = urllib.request.Request(
        f"{os.environ['DS_LITE_FAKE_PROVIDER_URL']}/{scenario}",
        data=b"{}",
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            status = response.status
            body = response.read()
    except urllib.error.HTTPError as exc:
        try:
            payload = json.loads(exc.read().decode("utf-8"))
            code = payload.get("error", {}).get("code", "unrecognized")
        except (UnicodeDecodeError, json.JSONDecodeError, AttributeError):
            code = "unrecognized"
        print(
            f"HTTP {exc.code} provider error code={code} response headers received {SECRET_MARKER}",
            file=sys.stderr,
            flush=True,
        )
        return 1
    except (OSError, urllib.error.URLError) as exc:
        print(
            f"connection reset before response header {SECRET_MARKER}",
            file=sys.stderr,
            flush=True,
        )
        return 1

    try:
        json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        print(
            f"HTTP {status} provider error code=invalid_response malformed response headers received {SECRET_MARKER}",
            file=sys.stderr,
            flush=True,
        )
        return 1

    if scenario == "ambiguous-transport":
        return 0
    emit({"type": "item.completed", "item": {"type": "agent_message", "text": "offline fake transport completed"}})
    emit({"type": "turn.completed", "usage": {"input_tokens": 2, "output_tokens": 3, "total_tokens": 5}})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
