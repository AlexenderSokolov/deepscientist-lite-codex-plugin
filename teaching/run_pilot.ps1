param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("prepare", "install", "preflight", "canary", "run", "resume", "score")]
    [string]$Action,
    [string]$WindowsRoot,
    [string]$WslRoot,
    [string]$PilotId,
    [string]$AuthorizationRef,
    [string]$CodexBin,
    [string]$WslBin = "wsl.exe",
    [double]$TimeoutSeconds = 0
)

$ErrorActionPreference = "Stop"
$env:PYTHONDONTWRITEBYTECODE = "1"
$env:PYTHONUTF8 = "1"
$Root = Split-Path -Parent $PSScriptRoot

if ([string]::IsNullOrWhiteSpace($WindowsRoot)) {
    throw "WindowsRoot is required for every pilot action."
}
if ($Action -in @("prepare", "preflight", "run", "resume", "score") -and [string]::IsNullOrWhiteSpace($WslRoot)) {
    throw "WslRoot is required for action '$Action'."
}
if ($Action -eq "prepare" -and ([string]::IsNullOrWhiteSpace($PilotId) -or [string]::IsNullOrWhiteSpace($AuthorizationRef))) {
    throw "PilotId and AuthorizationRef are required for prepare."
}
if ($Action -in @("preflight", "canary", "run", "resume") -and [string]::IsNullOrWhiteSpace($CodexBin)) {
    throw "CodexBin is required for action '$Action'."
}

if ($env:PYTHON_BIN) {
    $Python = $env:PYTHON_BIN
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    $Python = "python"
} elseif (Get-Command python3 -ErrorAction SilentlyContinue) {
    $Python = "python3"
} else {
    throw "Python 3.10+ was not found. Set PYTHON_BIN."
}

if ($Action -eq "score") {
    & $Python "$Root\teaching\pilot_score.py" score `
        --windows-root $WindowsRoot `
        --wsl-root $WslRoot
    exit $LASTEXITCODE
}

$Arguments = @(
    "$Root\teaching\pilot_runtime.py",
    $Action,
    "--windows-root", $WindowsRoot
)
if ($Action -in @("prepare", "preflight", "run", "resume")) {
    $Arguments += @("--wsl-root", $WslRoot)
}
if ($Action -eq "prepare") {
    $Arguments += @("--pilot-id", $PilotId, "--authorization-ref", $AuthorizationRef)
}
if ($Action -in @("preflight", "canary", "run", "resume")) {
    $Arguments += @("--codex-bin", $CodexBin)
}
if ($Action -eq "preflight") {
    $Arguments += @("--wsl-bin", $WslBin)
}
if ($Action -in @("canary", "run", "resume") -and $TimeoutSeconds -gt 0) {
    $Arguments += @("--timeout-seconds", $TimeoutSeconds)
}

& $Python @Arguments
exit $LASTEXITCODE
