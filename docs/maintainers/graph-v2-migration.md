# Graph v1 → v2 Migration

Graph v2 adds a non-negative `revision`, transactional writes, progression-only routes, semantic validation, and a portable external-path format.

## Before upgrading

1. Commit or otherwise back up the research project.
2. Run a read-only preview:

```bash
python path/to/ds_lite_state.py migrate --root . --dry-run
```

Graph v1 remains readable. The first state-changing command also attempts this migration automatically.

## Normal migration

```bash
python path/to/ds_lite_state.py migrate --root .
python path/to/ds_lite_state.py validate --root . --strict
```

The migration preserves the original file as `research/state/graph.v1.<timestamp>.json`. Backups are never automatically removed. Re-running migration on v2 is a no-op.

## Project-external paths

Migration stops with exit code 5 when v1 contains an absolute path outside the project. Map each external root explicitly:

```bash
python path/to/ds_lite_state.py migrate --root . \
  --external-map data=/absolute/path/to/data \
  --external-map baseline=/absolute/path/to/baseline
```

The graph stores only values such as `external://data/train/input.json`. Configure the corresponding local root without committing it:

```bash
export DS_LITE_EXTERNAL_DATA=/absolute/path/to/data
```

PowerShell:

```powershell
$env:DS_LITE_EXTERNAL_DATA = "D:\data"
```

Put reproducible environment setup in the relevant `run_*.sh`; do not store workstation absolute paths in graph JSON.

## Concurrent sessions

Read `status`, pass its revision to writes with `--expected-revision`, and refresh after every successful command. Exit code 4 means another session committed first; reload and reconcile both changes rather than retrying blindly.

## Compatibility

- Existing skill identifiers and the `ds_lite_state.py` entry point are unchanged.
- `link-artifact` remains as a deprecated alias for `link-path --type artifact` during v0.2.
- `status --json` remains accepted, although JSON is always the output.
- `trace` now defaults to progression edges only; use `--mode all` for legacy all-edge traversal.
