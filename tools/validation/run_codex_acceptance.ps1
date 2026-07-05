param(
    [Parameter(Mandatory = $true)]
    [string]$Output
)

$ErrorActionPreference = "Stop"
$env:PYTHONDONTWRITEBYTECODE = "1"
$env:PYTHONUTF8 = "1"
$PythonBin = if ($env:PYTHON_BIN) { $env:PYTHON_BIN } else { "python" }
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = (Resolve-Path (Join-Path $ScriptDir "..\..")).Path

& $PythonBin (Join-Path $ScriptDir "prepare_codex_acceptance.py") --repo-root $RepoRoot --output $Output
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$AuditArgs = @(
    (Join-Path $ScriptDir "audit_codex_acceptance.py"),
    "--root", $Output,
    "--record", (Join-Path $Output "acceptance-audit.json")
)
$CodexCommand = Get-Command codex -All -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandType -eq "Application" } |
    Select-Object -First 1
if ($CodexCommand) {
    $AuditArgs += @("--codex-bin", $CodexCommand.Source)
}
& $PythonBin @AuditArgs
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "Package prepared and structurally audited. Installation still requires /plugins in a new Codex session."
