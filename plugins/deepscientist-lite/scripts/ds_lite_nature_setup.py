#!/usr/bin/env python3
"""First-use setup and redacted capability checks for nature skills."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

SCHEMA = "ds-lite.nature-setup.v1"
REGISTRY_NAME = "nature-skill-registry.json"
SECRET_ENV_HINTS = ("API_KEY", "TOKEN", "PASSWORD", "SECRET", "CREDENTIAL")
KNOWN_ENV_KEYS = (
    "OPENAI_API_KEY",
    "NCBI_API_KEY",
    "CROSSREF_MAILTO",
    "SEMANTIC_SCHOLAR_API_KEY",
    "SCOPUS_API_KEY",
    "ELSEVIER_API_KEY",
    "SPRINGER_API_KEY",
    "GOOGLE_API_KEY",
    "GITHUB_TOKEN",
    "ZOTERO_API_KEY",
    "OPENALEX_EMAIL",
    "PUBMED_EMAIL",
    "OPENROUTER_API_KEY",
)
COMMANDS = ("python", "node", "npm", "latexmk", "git", "bash", "wsl", "codex")
ENV_NAME_RE = re.compile(r"\b[A-Z][A-Z0-9_]*(?:API_KEY|TOKEN|EMAIL|MAILTO|PASSWORD|SECRET)\b")
FALLBACK_RE = re.compile(r"fallback|no[- ]mcp|without mcp|stdlib|本地|无\s*MCP", re.IGNORECASE)
REQUIREMENT_RE = re.compile(r"^\s*([A-Za-z0-9_.-]+)")


class SetupError(RuntimeError):
    pass


def load_registry(script_path: Path) -> dict:
    path = script_path.resolve().parents[1] / "references" / REGISTRY_NAME
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SetupError("nature skill registry is unavailable") from exc
    if value.get("schema_version") != "ds-lite.nature-skill-registry.v1":
        raise SetupError("nature skill registry schema is unsupported")
    return value


def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _text_files(root: Path):
    for path in root.rglob("*"):
        if path.is_file() and path.suffix.lower() in {".md", ".yaml", ".yml", ".json", ".toml", ".py", ".js", ".ts"}:
            yield path


def _requirement_files(root: Path) -> list[Path]:
    return sorted(
        path for path in root.rglob("*")
        if path.is_file() and (
            path.name.lower().startswith("requirements") and path.suffix.lower() == ".txt"
            or path.name in {"pyproject.toml", "package.json", "package-lock.json"}
        )
    )


def _distribution_requirements(paths: list[Path]) -> list[str]:
    names: set[str] = set()
    for path in paths:
        if path.suffix.lower() != ".txt":
            continue
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeError):
            continue
        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith(("#", "-")):
                continue
            match = REQUIREMENT_RE.match(stripped)
            if match:
                names.add(match.group(1))
    return sorted(names, key=str.lower)


def capability_matrix(registry: dict) -> dict[str, dict]:
    root = repo_root()
    vendor = root / PurePosixPath(registry["upstream"]["vendor_root"]) / "skills"
    runtime = root / "plugins" / "deepscientist-lite" / "skills"
    matrix: dict[str, dict] = {}
    for item in registry.get("skills", []):
        name = item["skill"]
        source_root = vendor / name
        runtime_root = runtime / name
        text_parts: list[str] = []
        for path in _text_files(source_root):
            try:
                text_parts.append(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError):
                continue
        corpus = "\n".join(text_parts)
        requirement_paths = _requirement_files(source_root)
        signals = sorted(item.get("dependency_signals", {}).keys())
        external_effects: set[str] = {"filesystem"}
        if any(signal in signals for signal in ("mcp", "api", "browser", "download")):
            external_effects.add("network")
        if any(signal in signals for signal in ("python", "node", "latex", "browser")):
            external_effects.add("subprocess")
        manifest_required = (source_root / "manifest.yaml").is_file()
        route_complete = all(
            path.is_file()
            for path in (source_root / "SKILL.md", runtime_root / "SKILL.md", runtime_root / "provenance.json")
        ) and (not manifest_required or (runtime_root / "manifest.yaml").is_file())
        matrix[name] = {
            "route_complete": route_complete,
            "manifest_present": manifest_required,
            "local_scripts": sorted(
                path.relative_to(source_root).as_posix()
                for path in source_root.rglob("*")
                if path.is_file() and path.suffix.lower() in {".py", ".sh", ".js", ".ts", ".r"}
            ),
            "requirements": [path.relative_to(source_root).as_posix() for path in requirement_paths],
            "python_distributions": _distribution_requirements(requirement_paths),
            "environment_keys": sorted(set(ENV_NAME_RE.findall(corpus))),
            "dependency_signals": signals,
            "local_fallback": bool(FALLBACK_RE.search(corpus)),
            "playwright_optional": "playwright" in corpus.lower(),
            "external_effects": sorted(external_effects),
        }
    return matrix


def verify_snapshot(registry: dict) -> dict:
    root = repo_root()
    vendor = root / PurePosixPath(registry["upstream"]["vendor_root"]) / "skills"
    runtime = root / "plugins" / "deepscientist-lite" / "skills"
    mismatches: list[str] = []
    for item in registry.get("skills", []):
        name = item["skill"]
        source_root = vendor / name
        runtime_root = runtime / name
        source_skill = source_root / "SKILL.md"
        runtime_skill = runtime_root / "SKILL.md"
        if not source_skill.is_file() or not runtime_skill.is_file():
            mismatches.append(f"{name}:missing-skill")
            continue
        try:
            source_text = source_skill.read_text(encoding="utf-8")
            runtime_text = runtime_skill.read_text(encoding="utf-8")
            body = source_text.split("\n---", 1)[1].lstrip("\r\n") if source_text.startswith("---") else source_text
        except (OSError, UnicodeError, IndexError):
            mismatches.append(f"{name}:unreadable-skill")
            continue
        if body not in runtime_text:
            mismatches.append(f"{name}:source-body-mismatch")
        for source_path in source_root.rglob("*"):
            if not source_path.is_file() or source_path.name == "SKILL.md":
                continue
            relative = source_path.relative_to(source_root)
            runtime_path = runtime_root / relative
            if not runtime_path.is_file():
                mismatches.append(f"{name}:{relative.as_posix()}:missing")
            elif relative.as_posix() == "agents/openai.yaml":
                try:
                    agent_text = runtime_path.read_text(encoding="ascii")
                except (OSError, UnicodeError):
                    mismatches.append(f"{name}:agents/openai.yaml:invalid-adapter")
                else:
                    if "execution: bounded-and-redacted" not in agent_text or "external_effects: explicit-authorization" not in agent_text:
                        mismatches.append(f"{name}:agents/openai.yaml:missing-boundary")
            elif sha256(runtime_path) != sha256(source_path):
                mismatches.append(f"{name}:{relative.as_posix()}:hash-mismatch")
        provenance_path = runtime_root / "provenance.json"
        try:
            provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            mismatches.append(f"{name}:invalid-provenance")
        else:
            if provenance.get("upstream", {}).get("source_skill_sha256") != sha256(source_skill):
                mismatches.append(f"{name}:provenance-hash-mismatch")
    shared_path = root / PurePosixPath(registry["shared_layer"]["path"])
    shared_discoverable = (runtime / registry["shared_layer"]["name"]).is_dir()
    if not shared_path.is_dir():
        mismatches.append("nature-shared:missing")
    if shared_discoverable:
        mismatches.append("nature-shared:discoverable")
    return {
        "status": "passed" if not mismatches else "blocked",
        "skill_count": len(registry.get("skills", [])),
        "shared_layer_discoverable": shared_discoverable,
        "mismatches": mismatches,
    }


def requirement_observation(matrix: dict[str, dict]) -> dict[str, dict]:
    observed: dict[str, dict] = {}
    for name, item in matrix.items():
        distributions = {}
        for distribution in item["python_distributions"]:
            try:
                version = importlib.metadata.version(distribution)
            except importlib.metadata.PackageNotFoundError:
                distributions[distribution] = "missing"
            else:
                distributions[distribution] = f"installed:{version}"
        observed[name] = {
            "python_distributions": distributions,
            "environment_key_presence": {key: bool(os.environ.get(key)) for key in item["environment_keys"]},
        }
    return observed


def workspace_path(value: str) -> Path:
    if not value or "<" in value or ">" in value:
        raise SetupError("workspace must not contain a placeholder")
    candidate = Path(value).expanduser().resolve()
    if not candidate.is_dir():
        raise SetupError("workspace must be an existing directory")
    return candidate


def run_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{stamp}-{os.getpid()}"


def relative_ref(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return "external"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def detect_environment(workspace: Path, registry: dict) -> dict:
    env_presence = {key: bool(os.environ.get(key)) for key in KNOWN_ENV_KEYS}
    command_state = {command: bool(shutil.which(command)) for command in COMMANDS}
    local_config_candidates = [workspace / ".mcp.json", workspace / ".ds-lite" / "nature" / "mcp-config.json"]
    configured_files = [relative_ref(path, workspace) for path in local_config_candidates if path.is_file()]
    configured_mcp = bool(configured_files or os.environ.get("DS_LITE_MCP_CONFIG"))
    registry_signals = {}
    for item in registry.get("skills", []):
        registry_signals[item["skill"]] = sorted(item.get("dependency_signals", {}).keys())
    matrix = capability_matrix(registry)
    statuses = []
    if configured_mcp:
        statuses.append("ready")
    else:
        statuses.append("needs-config")
    if not command_state.get("python"):
        statuses.append("missing-dependency")
    if any(env_presence.values()):
        statuses.append("ready")
    else:
        statuses.append("needs-config")
    return {
        "environment_key_presence": env_presence,
        "command_availability": command_state,
        "local_mcp_config_refs": configured_files,
        "mcp_configured": configured_mcp,
        "skill_dependency_signals": registry_signals,
        "capability_matrix": matrix,
        "requirement_observation": requirement_observation(matrix),
        "status": sorted(set(statuses)),
        "policy": {
            "global_config_read": False,
            "global_config_write": False,
            "credential_values_persisted": False,
            "network_requested": False,
        },
    }


def _write_fresh(path: Path, value: object) -> None:
    if path.exists():
        raise SetupError(f"refusing to overwrite existing output: {path.name}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def guide_text(workspace: Path, report: dict) -> str:
    missing = [key for key, present in report["environment_key_presence"].items() if not present]
    missing_tools = [key for key, present in report["command_availability"].items() if not present]
    lines = [
        "# DeepScientist Lite Nature Skills 首次配置",
        "",
        "本引导只检查本地环境，不会读取或保存密钥，不会访问外部网络，也不会修改全局 Codex 配置。",
        "",
        "## 当前状态",
        f"- 工作区：`{workspace.name}`",
        f"- 状态：{', '.join(report['status'])}",
        f"- 本地 MCP 配置：{'已发现' if report['mcp_configured'] else '尚未发现'}",
        "",
        "## 配置步骤",
        "1. 只为需要的服务设置对应环境变量；不要把密钥写入项目文件。",
        "2. 需要 MCP 时，在工作区 `.ds-lite/nature/mcp-config.json` 中按模板填写命令和环境变量名。",
        "3. 重新运行 `doctor`，确认状态为 `ready` 后再执行外部检索、下载或发布动作。",
        "4. 缺少外部依赖时使用 skill 中的本地 fallback，并在结果中保留 `not-observed`。",
        "",
        "## 尚未配置的环境变量名",
    ]
    lines.extend(f"- `{key}`" for key in missing)
    lines.extend(["", "## 尚未发现的工具"])
    lines.extend(f"- `{key}`" for key in missing_tools)
    lines.extend(["", "## 安全边界", "- 不自动写入 `CODEX_HOME`、credential、marketplace 或系统配置。", "- 不保存 prompt、原始 JSON、原始 stderr、URL 中的认证内容或绝对工作站根目录。", "- 任何外部网络、下载、浏览器或发布动作都需要用户明确授权。", ""])
    return "\n".join(lines)


def run_setup(args: argparse.Namespace, *, apply_config: bool) -> dict:
    workspace = workspace_path(args.workspace)
    registry = load_registry(Path(__file__))
    report = detect_environment(workspace, registry)
    config_path = workspace / ".ds-lite" / "nature" / "integration-config.json"
    if apply_config and config_path.exists():
        raise SetupError("refusing to overwrite existing local integration-config.json")
    root = workspace / ".ds-lite" / "nature" / "runs" / f"nature-setup-{run_id()}"
    receipt = {
        "schema_version": SCHEMA,
        "run_id": root.name,
        "status": "ready" if report["status"] == ["ready"] else "needs-action",
        "failure_layer": "none" if report["status"] == ["ready"] else "environment-configuration",
        "workspace_ref": workspace.name,
        "registry": {
            "commit": registry["upstream"]["commit"],
            "skill_count": registry["runtime_skill_count"],
            "shared_discoverable": registry["shared_layer"]["discoverable"],
        },
        "observation": report,
        "raw_output_persisted": False,
        "secret_values_persisted": False,
        "next_action": "run-apply-after-explicit-local-config" if apply_config else "review-guide-and-configure-needed-integrations",
    }
    _write_fresh(root / "receipt.json", receipt)
    _write_fresh(root / "README.zh.md", guide_text(workspace, report))
    if apply_config:
        config = {
            "schema_version": "ds-lite.nature-integration-config.v1",
            "enabled": False,
            "mcp_servers": [],
            "environment_key_names": list(KNOWN_ENV_KEYS),
            "external_effects_require_authorization": True,
            "source_registry_ref": "plugins/deepscientist-lite/references/nature-skill-registry.json",
        }
        _write_fresh(config_path, config)
        receipt["next_action"] = "fill-local-config-and-rerun-verify"
    print(json.dumps({"status": receipt["status"], "receipt_ref": relative_ref(root / "receipt.json", workspace), "guide_ref": relative_ref(root / "README.zh.md", workspace), "skill_count": registry["runtime_skill_count"]}, ensure_ascii=True))
    return receipt


def inventory(args: argparse.Namespace) -> dict:
    registry = load_registry(Path(__file__))
    result = {
        "schema_version": "ds-lite.nature-skill-inventory.v1",
        "upstream_commit": registry["upstream"]["commit"],
        "skill_count": registry["runtime_skill_count"],
        "skills": [item["skill"] for item in registry["skills"]],
        "shared_layer_discoverable": registry["shared_layer"]["discoverable"],
        "capability_matrix": capability_matrix(registry),
    }
    print(json.dumps(result, ensure_ascii=True))
    return result


def verify(args: argparse.Namespace) -> dict:
    workspace = workspace_path(args.workspace)
    config_path = workspace / ".ds-lite" / "nature" / "integration-config.json"
    if not config_path.is_file():
        raise SetupError("local integration-config.json is missing")
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SetupError("local integration-config.json is invalid") from exc
    if config.get("schema_version") != "ds-lite.nature-integration-config.v1" or config.get("enabled") is not False:
        raise SetupError("local integration config must remain explicit and disabled until configured")
    snapshot = verify_snapshot(load_registry(Path(__file__)))
    if snapshot["status"] != "passed":
        raise SetupError("nature vendor/runtime snapshot verification failed")
    result = {"status": "passed", "snapshot_status": snapshot["status"], "config_ref": relative_ref(config_path, workspace), "secret_values_persisted": False, "network_requested": False}
    print(json.dumps(result, ensure_ascii=True))
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Inspect and guide nature skill integrations without global writes.")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("inventory")
    for name in ("doctor", "onboarding", "apply", "verify"):
        command = sub.add_parser(name)
        command.add_argument("--workspace", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "inventory":
            inventory(args)
        elif args.command == "verify":
            verify(args)
        else:
            run_setup(args, apply_config=args.command == "apply")
    except SetupError as exc:
        print(json.dumps({"status": "blocked", "failure_layer": "nature-setup", "message": str(exc), "secret_values_persisted": False}, ensure_ascii=True))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
