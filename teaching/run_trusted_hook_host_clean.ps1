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
$expectedVersion = if ($env:CODEX_EXPECTED_VERSION) { $env:CODEX_EXPECTED_VERSION } else { "0.144.5" }
$expectedSha256 = if ($env:CODEX_EXPECTED_SHA256) { $env:CODEX_EXPECTED_SHA256 } else { "EFDB3540EF74B9909408C8D38DA79483454797B36F471E3E004FC2BF2B70E22A" }
& $python (Join-Path $PSScriptRoot "trusted_hook_run.py") --codex-bin $CodexBin --codex-home $CodexHome --workspace $Workspace --hook-events $HookEvents --output $Output --prompt $Prompt --expected-version $expectedVersion --expected-sha256 $expectedSha256
exit $LASTEXITCODE
