#!/usr/bin/env python3
"""Probe a Responses SSE terminal event without retaining provider content."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import urllib.error
import urllib.request


TERMINAL_EVENTS = {"response.completed", "response.failed", "response.incomplete"}


def _event_name(line: bytes) -> str | None:
    try:
        decoded = line.decode("utf-8", errors="replace").strip()
    except UnicodeError:
        return None
    if not decoded.startswith("event: "):
        return None
    event = decoded.removeprefix("event: ").strip()
    return event or None


def probe(base_url: str, model: str, api_key: str, timeout: int, *, direct_egress: bool = False) -> dict[str, object]:
    url = base_url.rstrip("/") + "/responses"
    payload = {
        "model": model,
        "input": [{"role": "user", "content": [{"type": "input_text", "text": "End now."}]}],
        "stream": True,
        "store": False,
    }
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json", "Accept": "text/event-stream"},
        method="POST",
    )
    events: set[str] = set()
    status = "unknown"
    failure = "none"
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({})) if direct_egress else urllib.request.build_opener()
    try:
        with opener.open(request, timeout=timeout) as response:
            status = str(response.status)
            for line in response:
                event = _event_name(line)
                if event is not None:
                    events.add(event)
    except urllib.error.HTTPError as exc:
        status = str(exc.code)
        failure = "http"
    except (OSError, ValueError) as exc:
        failure = f"{type(exc).__name__}:{hashlib.sha256(str(exc).encode('utf-8')).hexdigest()}"
    return {
        "http_status": status,
        "event_types": sorted(events),
        "terminal_event_observed": bool(events & TERMINAL_EVENTS),
        "failure": failure,
        "direct_egress_requested": direct_egress,
        "raw_provider_content_persisted": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe a minimal Responses stream without retaining content.")
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--api-key-env", default="OPENAI_API_KEY")
    parser.add_argument("--timeout", type=int, default=45)
    parser.add_argument("--direct-egress", action="store_true", help="Bypass inherited proxy variables for this explicit probe.")
    args = parser.parse_args()
    key = os.environ.get(args.api_key_env, "")
    if not key:
        print(json.dumps({"status": "blocked", "failure": "credential-env-missing"}, ensure_ascii=True))
        return 2
    result = probe(args.base_url, args.model, key, args.timeout, direct_egress=args.direct_egress)
    print(json.dumps(result, ensure_ascii=True))
    return 0 if result["terminal_event_observed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
