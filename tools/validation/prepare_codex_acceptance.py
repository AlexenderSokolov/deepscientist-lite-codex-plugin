#!/usr/bin/env python3
"""Prepare a fresh, isolated Codex acceptance package.

This command copies the plugin and creates deterministic teaching fixtures. It
does not register a marketplace, install a plugin, or modify Codex user state.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "ds-lite.codex-acceptance.v1"
PLUGIN_NAME = "deepscientist-lite"
SAFE_NAME = re.compile(r"^[a-z][a-z0-9.-]*$")


class PreparationError(RuntimeError):
    pass


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value.rstrip() + "\n", encoding="utf-8")


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def git_head(repo_root: Path) -> str | None:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_root,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
    )
    return completed.stdout.strip() if completed.returncode == 0 else None


def acceptance_version(release_version: str, cachebuster: str) -> str:
    if not SAFE_NAME.fullmatch(cachebuster):
        raise PreparationError("cachebuster must start with a letter and contain only lowercase letters, digits, dots, or hyphens")
    public_version = release_version.split("+", 1)[0]
    return f"{public_version}+codex.{cachebuster}"


def run_lab(repo_root: Path, output: Path, lab: str, case: str = "clean") -> None:
    command = [
        sys.executable,
        str(repo_root / "teaching" / "lab_runner.py"),
        "--lab",
        lab,
        "--mode",
        "student",
        "--case",
        case,
        "--output",
        str(output),
    ]
    completed = subprocess.run(
        command,
        cwd=repo_root,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
    )
    if completed.returncode != 0:
        detail = (completed.stdout + completed.stderr).strip()
        raise PreparationError(f"failed to prepare {lab}/{case}: {detail}")


def manual_guide(marketplace_name: str, version: str) -> str:
    return f"""# Codex 人工验收入口

此目录是隔离副本，不会自动修改 Codex 配置。副本版本为 `{version}`。

## 安装边界

1. 在 Codex CLI 中执行 `codex plugin marketplace add <此目录>`，只添加 marketplace 来源。
2. 重启 Codex，在 `/plugins` 中选择 `{marketplace_name}`，再安装 `deepscientist-lite`。
3. 新建线程，确认界面显示副本版本，并能发现六个技能。

“marketplace 已添加”不等于“插件已安装”。如果当前 Codex 构建没有 `/plugins` 或相应插件浏览能力，记录为宿主能力缺失，不要删除旧缓存或伪造安装成功。

## 建议执行顺序

- `projects/manual-main/`：从零测试 intake → scout → idea → experiment → review → analysis。
- `fixtures/evidence-clean/`、`evidence-tampered/`、`evidence-threshold-miss/`：分别测试通过、哈希篡改和阈值失败。
- `fixtures/branches/`：检查 A 退化、B 稳定、C 标签泄漏三条路线。
- `fixtures/route/`、`paths/`、`revision/`：检查路线、路径和 revision 协议。

每个线程都记录提示词、线程标识、实际文件证据和判定；线程失败但没有产生文件时，归类为宿主基础设施问题，不归咎于插件协议。
"""


def prepare(repo_root: Path, output: Path, cachebuster: str, marketplace_name: str, with_fixtures: bool) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    output = output.resolve()
    if output.exists():
        raise PreparationError(f"output already exists; choose a fresh path: {output}")
    if not SAFE_NAME.fullmatch(marketplace_name):
        raise PreparationError("marketplace name must start with a letter and contain only lowercase letters, digits, dots, or hyphens")

    source_plugin = repo_root / "plugins" / PLUGIN_NAME
    source_manifest = source_plugin / ".codex-plugin" / "plugin.json"
    marketplace_source = repo_root / ".agents" / "plugins" / "marketplace.json"
    lab_runner = repo_root / "teaching" / "lab_runner.py"
    for required in (source_manifest, marketplace_source, lab_runner):
        if not required.exists():
            raise PreparationError(f"required source file is missing: {required}")

    output.parent.mkdir(parents=True, exist_ok=True)
    output.mkdir()
    copied_plugin = output / "plugins" / PLUGIN_NAME
    shutil.copytree(
        source_plugin,
        copied_plugin,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )

    plugin_manifest = read_json(copied_plugin / ".codex-plugin" / "plugin.json")
    release_version = str(plugin_manifest["version"])
    version = acceptance_version(release_version, cachebuster)
    plugin_manifest["version"] = version
    write_json(copied_plugin / ".codex-plugin" / "plugin.json", plugin_manifest)

    marketplace = read_json(marketplace_source)
    marketplace["name"] = marketplace_name
    interface = marketplace.setdefault("interface", {})
    interface["displayName"] = f"DeepScientist Lite acceptance ({cachebuster})"
    write_json(output / ".agents" / "plugins" / "marketplace.json", marketplace)

    fixture_specs = [
        ("evidence-clean", "evidence", "clean"),
        ("evidence-tampered", "evidence", "tampered"),
        ("evidence-threshold-miss", "evidence", "threshold-miss"),
        ("branches", "branches", "clean"),
        ("route", "route", "clean"),
        ("paths", "paths", "clean"),
        ("revision", "revision", "clean"),
    ]
    fixture_paths: list[str] = []
    if with_fixtures:
        for directory, lab, case in fixture_specs:
            destination = output / "fixtures" / directory
            run_lab(repo_root, destination, lab, case)
            fixture_paths.append(destination.relative_to(output).as_posix())
    (output / "projects" / "manual-main").mkdir(parents=True)

    record: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source": {
            "repository": str(repo_root),
            "git_head": git_head(repo_root),
            "release_version": release_version,
        },
        "marketplace": {
            "name": marketplace_name,
            "manifest": ".agents/plugins/marketplace.json",
            "registration": "not-attempted",
        },
        "plugin": {
            "name": PLUGIN_NAME,
            "version": version,
            "path": f"plugins/{PLUGIN_NAME}",
            "installation": "not-verified",
            "expected_skill_count": 6,
        },
        "fixtures": fixture_paths,
        "manual_project": "projects/manual-main",
        "safety": {
            "modifies_codex_configuration": False,
            "overwrites_existing_output": False,
            "removes_existing_files": False,
        },
    }
    write_json(output / "acceptance.json", record)
    write_text(output / "ACCEPTANCE.zh.md", manual_guide(marketplace_name, version))
    return record


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Prepare an isolated DeepScientist Lite Codex acceptance package.")
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--output", type=Path, required=True, help="Fresh output directory; existing paths are refused.")
    parser.add_argument("--cachebuster", default=f"local-{utc_stamp()}")
    parser.add_argument("--marketplace-name", help="Unique local marketplace name; defaults to the cachebuster.")
    parser.add_argument("--without-fixtures", action="store_true", help="Copy the plugin without generating teaching fixtures.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    marketplace_name = args.marketplace_name or f"ds-lite-acceptance-{args.cachebuster}"
    try:
        result = prepare(args.repo_root, args.output, args.cachebuster, marketplace_name, not args.without_fixtures)
    except (PreparationError, OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"Prepared acceptance package: {args.output.resolve()}")
    print("Next: add this directory as a marketplace source, then install the plugin from /plugins in a new Codex session.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
