param(
    [Parameter(Mandatory = $true)] [string]$CodexBin,
    [Parameter(Mandatory = $true)] [string]$CodexHome,
    [Parameter(Mandatory = $true)] [string]$Workspace,
    [Parameter(Mandatory = $true)] [string]$HookEvents,
    [Parameter(Mandatory = $true)] [string]$Output,
    [Parameter(Mandatory = $true)] [string]$Prompt
)
$ErrorActionPreference = "Stop"
foreach ($value in @($CodexBin, $CodexHome, $Workspace, $HookEvents, $Output)) {
    if ($value -match '<[^>]+>') { throw "placeholder path is not allowed" }
}
foreach ($pathValue in @($CodexBin, $CodexHome, $Workspace, $HookEvents)) {
    if (-not (Test-Path -LiteralPath $pathValue)) { throw "required host path does not exist" }
}
$env:CODEX_HOME = (Resolve-Path -LiteralPath $CodexHome).Path
$env:DS_LITE_HOOK_ACCEPTANCE_DIR = (Resolve-Path -LiteralPath $HookEvents).Path
$env:PYTHONDONTWRITEBYTECODE = "1"
$env:PYTHONUTF8 = "1"
$env:PYTHONPATH = (Split-Path -Parent $PSScriptRoot)
$python = if ($env:PYTHON_BIN) { $env:PYTHON_BIN } else { "python" }
& $python (Join-Path $PSScriptRoot "trusted_hook_run.py") --codex-bin $CodexBin --codex-home $CodexHome --workspace $Workspace --hook-events $HookEvents --output $Output --prompt $Prompt
exit $LASTEXITCODE
