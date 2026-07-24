"""Prepare a fresh, non-sensitive Codex host for trusted-hook acceptance.

This module is intentionally invoked as a normal Python program. Shell launchers
pass paths through argv; no shell ever embeds Python source code.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from teaching.pilot_runtime import clone_nonsecret_provider_config

EXPECTED_SHA256 = "EFDB3540EF74B9909408C8D38DA79483454797B36F471E3E004FC2BF2B70E22A"
EXPECTED_VERSION = "0.144.5"


class PreparationError(RuntimeError):
    pass


def _reject_placeholder(value: str) -> None:
    if "<" in value or ">" in value:
        raise PreparationError("placeholder path is not allowed")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def _run_install(codex_bin: Path, repo_root: Path, home: Path) -> None:
    env = {"CODEX_HOME": str(home)}
    import os
    child_env = os.environ.copy()
    child_env.update(env)
    for args in (("plugin", "marketplace", "add", str(repo_root)),
                 ("plugin", "add", "deepscientist-lite@deepscientist-lite")):
        result = subprocess.run([str(codex_bin), *args], env=child_env,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                check=False)
        if result.returncode != 0:
            raise PreparationError("codex plugin installation failed")


def prepare(*, codex_bin: Path | str, source_home: Path | str,
            repo_root: Path | str, pilot_root: Path | str,
            install: bool = True) -> dict[str, Any]:
    codex = Path(codex_bin)
    source = Path(source_home)
    repo = Path(repo_root)
    root = Path(pilot_root)
    for value in (str(codex), str(source), str(repo), str(root)):
        _reject_placeholder(value)
    if not codex.is_file() or not source.is_dir() or not repo.is_dir():
        raise PreparationError("required path does not exist")
    if _sha256(codex) != EXPECTED_SHA256:
        raise PreparationError("Codex binary SHA-256 mismatch")
    try:
        root.mkdir(parents=True)
    except FileExistsError as exc:
        raise PreparationError("fresh host already exists; refusing overwrite") from exc
    home = root / "codex-home"
    workspace = root / "workspace"
    events = root / "hook-events"
    for path in (home, workspace, events):
        path.mkdir()
    if install:
        _run_install(codex, repo, home)
    lines, clone_status = clone_nonsecret_provider_config(source, home)
    if not clone_status.get("provider_route_copied") or not clone_status.get("catalog_copied"):
        raise PreparationError("non-secret provider route/catalog incomplete")
    config = home / "config.toml"
    existing = config.read_text(encoding="utf-8") if config.exists() else ""
    # Keep plugin/marketplace tables created by Codex while placing route keys first.
    config.write_text("\n".join(lines) + ("\n" + existing if existing else "\n"), encoding="utf-8", newline="\n")
    try:
        try:
            from .toml_compat import tomllib
        except ImportError:
            from toml_compat import tomllib
        parsed = tomllib.loads(config.read_text(encoding="utf-8"))
    except Exception as exc:
        raise PreparationError("generated TOML failed validation") from exc
    provider = parsed.get("model_providers", {}).get("custom", {})
    valid = (parsed.get("model_provider") == "custom"
             and provider.get("requires_openai_auth") is True
             and provider.get("env_key") == "OPENAI_API_KEY"
             and provider.get("request_max_retries") == 0
             and provider.get("stream_max_retries") == 0)
    if not valid:
        raise PreparationError("generated route fidelity validation failed")
    receipt = {
        "schema_version": "ds-lite.trusted-host-preparation.v1",
        "status": "prepared",
        "codex_version": EXPECTED_VERSION,
        "codex_sha256": EXPECTED_SHA256,
        "route_fidelity": clone_status.get("route_fidelity", {}),
        "config_validated": True,
        "retries": {"request_max_retries": 0, "stream_max_retries": 0},
        "plugin_install_attempted": bool(install),
        "raw_output_persisted": False,
        "secret_material_persisted": False,
        "paths": {"home_ref": "codex-home", "workspace_ref": "workspace", "hook_events_ref": "hook-events"},
    }
    (root / "preparation.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8", newline="\n")
    return receipt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--codex-bin", required=True)
    parser.add_argument("--source-home", required=True)
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--pilot-root", required=True)
    parser.add_argument("--no-install", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = prepare(codex_bin=args.codex_bin, source_home=args.source_home,
                         repo_root=args.repo_root, pilot_root=args.pilot_root,
                         install=not args.no_install)
    except PreparationError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(json.dumps({"status": result["status"], "codex_version": result["codex_version"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
