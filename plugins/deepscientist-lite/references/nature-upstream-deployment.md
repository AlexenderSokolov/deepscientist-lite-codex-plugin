# Nature Skills Upstream Deployment Mapping

This integration is pinned to `nature-skills` commit
`91862221b39f7ca16d52ae0e1e9cb6c2bb31a96b`. The vendored README is the
deployment authority. DS Lite preserves the upstream directory model while
avoiding silent writes to a user's global Codex installation.

## Upstream Command Mapping

| Upstream README instruction | DS Lite behavior | Verification |
|---|---|---|
| `scripts/update-codex-skills.sh --pull` | The fixed full snapshot is vendored under the plugin and exposed through 17 runtime skill directories. It is not copied into `~/.codex/skills`. | `ds_lite_nature_setup.py inventory` |
| `scripts/update-codex-skills.sh --check` | Runtime files, complete directories, shared layer, provenance, and approved adapter differences are compared with the pinned snapshot. | `ds_lite_nature_setup.py verify --workspace <path>` |
| Preserve complete skill directories | `SKILL.md`, manifests, static fragments, references, scripts, templates, tests, and assets remain available. | `nature_runtime_acceptance.py` |
| Preserve `nature-shared` | The shared layer is retained internally and must not become a user-discoverable skill. | snapshot and runtime acceptance receipts |
| Install Python requirements as needed | `doctor` reports requirement files and installed distribution observations. It does not install packages. | capability matrix |
| Install Playwright Chromium for CNIPA | `doctor` reports the optional browser requirement. Missing Chromium remains `not-observed`. | capability matrix |
| Set `PUBMED_EMAIL` for academic-search MCP | Only the variable's presence is observed. The value is never persisted. | setup receipt |
| Configure Scopus and ScienceDirect credentials locally | Only allow-listed environment variable names and project-local MCP configuration are reported. | onboarding guide |

## Runtime Acceptance

Run one of the following wrappers. They pass paths through argv and do not
embed Python source in a shell string.

```powershell
powershell.exe -NoProfile -NonInteractive -File .\teaching\run_nature_runtime_acceptance.ps1
```

```bash
bash teaching/run_nature_runtime_acceptance.sh
```

The fresh-only `ds-lite.nature-runtime-acceptance.v1` receipt proves local
loading, parsing, provenance, and dependency classification. It does not prove
external MCP, API, browser, download, provider, Hook, Desktop, delegation,
matched-effect, cache, or release behavior.
