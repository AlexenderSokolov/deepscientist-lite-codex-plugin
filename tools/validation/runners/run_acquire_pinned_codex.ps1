param([string]$OutputRoot)
$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path
$OutputRoot = if ($OutputRoot) { $OutputRoot } elseif ($env:TEMP_ROOT) { $env:TEMP_ROOT } else { Join-Path $repoRoot ("research\.validation-tmp\codex-pin-" + $PID) }
$python = if ($env:PYTHON_BIN) { $env:PYTHON_BIN } else { "python" }
& $python (Join-Path $repoRoot "tools\validation\acquire_pinned_codex.py") --output-root $OutputRoot
exit $LASTEXITCODE
