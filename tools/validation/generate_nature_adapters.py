#!/usr/bin/env python3
"""Generate DS Lite entry metadata around the vendored nature-skills tree."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

COMMIT = "91862221b39f7ca16d52ae0e1e9cb6c2bb31a96b"
SKILLS = [
    "nature-academic-search",
    "nature-citation",
    "nature-data",
    "nature-downloader",
    "nature-experiment-log",
    "nature-figure",
    "nature-literature-pipeline",
    "nature-paper-to-patent",
    "nature-paper2ppt",
    "nature-polishing",
    "nature-proposal-writer",
    "nature-reader",
    "nature-ref-verifier",
    "nature-response",
    "nature-reviewer",
    "nature-statistics",
    "nature-writing",
]


class GenerationError(RuntimeError):
    pass


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def source_description(text: str, name: str) -> str:
    match = re.search(r"^description:\s*(.*?)(?=^version:|^author:|^---$)", text, re.MULTILINE | re.DOTALL)
    value = match.group(1) if match else ""
    value = re.sub(r"\s+", " ", value).strip(" >-")
    if len(value) < 30:
        value = f"the complete {name} upstream workflow with its local references and scripts"
    return f"Use the complete {name} workflow, preserving its upstream routing and supporting materials. {value[:700]}"


def body_without_frontmatter(text: str) -> str:
    if not text.startswith("---"):
        return text
    end = text.find("\n---", 3)
    if end < 0:
        raise GenerationError("invalid upstream frontmatter")
    return text[end + len("\n---"):].lstrip("\r\n")


def dependency_tokens(skill_root: Path) -> dict[str, list[str]]:
    terms = {
        "mcp": re.compile(r"\bMCP\b|mcp", re.IGNORECASE),
        "api": re.compile(r"\bAPI\b|api[_ -]key|endpoint", re.IGNORECASE),
        "browser": re.compile(r"browser|playwright|cdp|chrom(e|ium)", re.IGNORECASE),
        "download": re.compile(r"download|downloader|fetch", re.IGNORECASE),
        "latex": re.compile(r"latex|xelatex|latexmk", re.IGNORECASE),
        "node": re.compile(r"\bnode\b|npm|typescript", re.IGNORECASE),
        "python": re.compile(r"\bpython\b|pip|pyproject", re.IGNORECASE),
    }
    matched: dict[str, list[str]] = {key: [] for key in terms}
    for path in skill_root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in {".md", ".yaml", ".yml", ".json", ".py", ".js", ".ts", ".toml"}:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
        for key, pattern in terms.items():
            if pattern.search(text):
                matched[key].append(path.relative_to(skill_root).as_posix())
    return {key: sorted(set(value)) for key, value in matched.items() if value}


def generate(repo_root: Path) -> dict[str, object]:
    vendor_root = repo_root / "plugins" / "deepscientist-lite" / "vendor" / "nature-skills" / COMMIT / "skills"
    runtime_root = repo_root / "plugins" / "deepscientist-lite" / "skills"
    if not vendor_root.is_dir():
        raise GenerationError("nature vendor snapshot is missing")
    inventory = []
    for name in SKILLS:
        source = vendor_root / name
        runtime = runtime_root / name
        source_skill = source / "SKILL.md"
        if not source_skill.is_file() or not runtime.is_dir():
            raise GenerationError(f"missing nature skill snapshot: {name}")
        original = source_skill.read_text(encoding="utf-8")
        description = source_description(original, name)
        body = body_without_frontmatter(original)
        description = re.sub(r"\s+", " ", description).replace(":", ";")
        preamble = f"""---\nname: {name}\ndescription: {description}\n---\n\n# DS Lite Integration Boundary\n\nThis entry preserves the complete upstream {name} workflow at commit `{COMMIT}`.\nUse the upstream manifest, static fragments, references, scripts, templates, and tests\nthat remain in this directory; this file is not a summary replacement.\n\nBefore using any MCP, external API, browser, downloader, LaTeX, Node, or Python\nintegration, run `python plugins/deepscientist-lite/scripts/ds_lite_nature_setup.py doctor --workspace .`.\nRecord only redacted status and relative evidence references. Missing dependencies are\n`not-observed` or `blocked`, never silently treated as available.\n\nRead [responsible-exploration-covenant.md](../../references/responsible-exploration-covenant.md) first.\nEvery invocation follows DS Lite `start / progress / end`: state the target, facts,\nauthorization, actual action, evidence, failure layer, unverified items, and one next\naction. Do not save prompts, credentials, raw responses, hidden reasoning, or absolute\nworkstation paths.\n\n## Preserved Upstream Workflow\n\n"""
        (runtime / "SKILL.md").write_text(preamble + body, encoding="utf-8", newline="\n")
        agents = runtime / "agents"
        agents.mkdir(parents=True, exist_ok=True)
        (agents / "openai.yaml").write_text(
            f"""name: {name}\ndescription: Use the complete vendored {name} workflow with DS Lite evidence and dependency boundaries.\npolicy:\n  allow_implicit_invocation: true\n  execution: bounded-and-redacted\n  external_effects: explicit-authorization\n""",
            encoding="ascii",
            newline="\n",
        )
        provenance = {
            "schema_version": "ds-lite.nature-skill-provenance.v1",
            "skill": name,
            "upstream": {
                "repository": "https://github.com/Yuan1z0825/nature-skills",
                "commit": COMMIT,
                "license": "Apache-2.0",
                "source_path": f"skills/{name}",
                "source_skill_sha256": sha256(source_skill),
            },
            "runtime_path": f"plugins/deepscientist-lite/skills/{name}",
            "preserved_material": ["SKILL.md", "manifest.yaml", "static", "references", "scripts", "templates", "tests"],
            "adaptations": ["DS Lite lifecycle protocol", "dependency/onboarding boundary", "relative evidence policy", "redacted failure handling"],
            "dependency_signals": dependency_tokens(source),
            "nature_shared_internal": True,
        }
        (runtime / "provenance.json").write_text(json.dumps(provenance, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
        inventory.append(provenance)
    registry = {
        "schema_version": "ds-lite.nature-skill-registry.v1",
        "upstream": {
            "repository": "https://github.com/Yuan1z0825/nature-skills",
            "commit": COMMIT,
            "license": "Apache-2.0",
            "vendor_root": f"plugins/deepscientist-lite/vendor/nature-skills/{COMMIT}",
        },
        "runtime_skill_count": len(SKILLS),
        "shared_layer": {"name": "nature-shared", "discoverable": False, "path": "plugins/deepscientist-lite/references/nature-shared"},
        "skills": inventory,
    }
    registry_path = repo_root / "plugins" / "deepscientist-lite" / "references" / "nature-skill-registry.json"
    registry_path.write_text(json.dumps(registry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    return registry


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate complete nature skill runtime adapters.")
    parser.add_argument("--repo-root", default=".")
    args = parser.parse_args(argv)
    try:
        registry = generate(Path(args.repo_root).resolve())
    except (GenerationError, OSError, UnicodeError) as exc:
        print(json.dumps({"status": "blocked", "failure_layer": "nature-generation", "message": str(exc)}, ensure_ascii=True))
        return 1
    print(json.dumps({"status": "passed", "skill_count": registry["runtime_skill_count"], "shared_discoverable": False}, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
