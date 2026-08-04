"""Prepare a fresh, non-sensitive Codex host for trusted-hook acceptance.

This module is intentionally invoked as a normal Python program. Shell launchers
pass paths through argv; no shell ever embeds Python source code.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
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


def _canonical_workspace_key(workspace: Path) -> str:
    """Return the key Codex uses for a trusted project workspace."""
    return os.path.normcase(os.path.realpath(workspace))


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


def _candidate_identity(repo_root: Path) -> dict[str, Any]:
    plugin_root = repo_root / "plugins" / "deepscientist-lite-core"
    try:
        manifest = json.loads((plugin_root / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
        hooks = json.loads((plugin_root / "hooks" / "hooks.json").read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PreparationError("split Core candidate identity is unavailable") from exc
    skills = sorted(
        path.name for path in (plugin_root / "skills").iterdir()
        if path.is_dir() and (path / "SKILL.md").is_file()
    )
    digest = hashlib.sha256()
    files = sorted(
        path for path in plugin_root.rglob("*")
        if path.is_file()
        and "__pycache__" not in path.parts
        and path.suffix.lower() not in {".pyc", ".pyo"}
    )
    for path in files:
        relative = path.relative_to(plugin_root).as_posix().encode("utf-8")
        content = path.read_bytes()
        digest.update(relative + b"\0" + hashlib.sha256(content).digest())
    if manifest.get("name") != "deepscientist-lite" or manifest.get("version") != "0.9.0-beta.1":
        raise PreparationError("split Core manifest does not match the formal candidate")
    return {
        "plugin": manifest["name"],
        "version": manifest["version"],
        "skill_count": len(skills),
        "skills": skills,
        "hook_events": sorted(hooks.get("hooks", {})),
        "source_sha256": digest.hexdigest(),
    }


def prepare(*, codex_bin: Path | str, source_home: Path | str,
            repo_root: Path | str, pilot_root: Path | str,
            install: bool = True, expected_version: str = EXPECTED_VERSION,
            expected_sha256: str = EXPECTED_SHA256) -> dict[str, Any]:
    codex = Path(codex_bin)
    source = Path(source_home)
    repo = Path(repo_root)
    root = Path(pilot_root)
    for value in (str(codex), str(source), str(repo), str(root)):
        _reject_placeholder(value)
    if not codex.is_file() or not source.is_dir() or not repo.is_dir():
        raise PreparationError("required path does not exist")
    if not expected_version.strip():
        raise PreparationError("Codex version pin must be non-empty")
    expected_sha256 = expected_sha256.upper()
    if re.fullmatch(r"[0-9A-F]{64}", expected_sha256) is None:
        raise PreparationError("Codex SHA-256 pin must contain 64 hexadecimal characters")
    if _sha256(codex) != expected_sha256:
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
    candidate = {"status": "not-observed", "reason": "installation-skipped"}
    if install:
        candidate = _candidate_identity(repo)
        _run_install(codex, repo, home)
    lines, clone_status = clone_nonsecret_provider_config(source, home)
    if not clone_status.get("provider_route_copied"):
        raise PreparationError("non-secret provider route is incomplete")
    # A catalog is optional in Codex config. When configured it must have
    # copied successfully; when absent, the verified provider route remains
    # sufficient for a one-shot canary.
    if clone_status.get("catalog_configured") and not clone_status.get("catalog_copied"):
        raise PreparationError("configured non-secret model catalog was not copied")
    config = home / "config.toml"
    existing = config.read_text(encoding="utf-8") if config.exists() else ""
    workspace_key = _canonical_workspace_key(workspace)
    trust_table = f'\n\n[projects.{json.dumps(workspace_key)}]\ntrust_level = "trusted"\n'
    # Keep plugin/marketplace tables created by Codex while placing route and
    # formal project-trust keys ahead of them.
    config.write_text("\n".join(lines) + trust_table + existing, encoding="utf-8", newline="\n")
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
             and provider.get("stream_max_retries") == 0
             and parsed.get("projects", {}).get(workspace_key, {}).get("trust_level") == "trusted")
    if not valid:
        raise PreparationError("generated route fidelity validation failed")
    receipt = {
        "schema_version": "ds-lite.trusted-host-preparation.v1",
        "status": "prepared",
        "codex_version": expected_version,
        "codex_sha256": expected_sha256,
        "route_fidelity": clone_status.get("route_fidelity", {}),
        "config_validated": True,
        "workspace_trust_configured": True,
        "retries": {"request_max_retries": 0, "stream_max_retries": 0},
        "plugin_install_attempted": bool(install),
        "candidate": candidate,
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
    parser.add_argument("--expected-version", default=EXPECTED_VERSION)
    parser.add_argument("--expected-sha256", default=EXPECTED_SHA256)
    parser.add_argument("--no-install", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = prepare(codex_bin=args.codex_bin, source_home=args.source_home,
                         repo_root=args.repo_root, pilot_root=args.pilot_root,
                         install=not args.no_install,
                         expected_version=args.expected_version,
                         expected_sha256=args.expected_sha256)
    except PreparationError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(json.dumps({"status": result["status"], "codex_version": result["codex_version"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
