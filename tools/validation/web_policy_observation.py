#!/usr/bin/env python3
"""Write a redacted receipt when public Web policy rejects a request preflight."""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


POLICY = {"public_only": True, "authenticated": False, "submitted_forms": False, "cookies_persisted": False}


def _extensions_module():
    script = Path(__file__).resolve().parents[2] / "plugins" / "deepscientist-lite-web" / "scripts" / "ds_lite_extensions.py"
    spec = importlib.util.spec_from_file_location("ds_lite_extensions_policy", script)
    if spec is None or spec.loader is None:
        raise RuntimeError("Web policy module is unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def observe(url: str, allowed_domain: list[str]) -> dict[str, object]:
    module = _extensions_module()
    try:
        module._validate_public_uri(url)
        module._validate_domain_scope(url, allowed_domain)
    except module.ExtensionProtocolError as exc:
        return {"schema_version": "ds-lite.web-failure-observation.v1", "status": "observed", "failure_layer": "policy",
                "observed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"), "operation": "fetch-preflight",
                "reason": str(exc)[:500], "policy": POLICY, "extensions": {}}
    raise ValueError("request passed policy preflight; refusing to fabricate a rejection observation")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Observe a DS Lite public Web policy refusal without network access.")
    parser.add_argument("--url", required=True)
    parser.add_argument("--allowed-domain", action="append", default=[])
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    output = Path(args.output).expanduser().resolve()
    if output.exists():
        print(json.dumps({"status": "blocked", "reason": "output-exists"}))
        return 2
    try:
        result = observe(args.url, args.allowed_domain)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except (OSError, UnicodeError, ValueError, RuntimeError) as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps({"status": result["status"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
