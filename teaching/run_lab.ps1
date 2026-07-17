param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("quickstart", "evidence", "branches", "route", "paths", "revision", "matched-pilot")]
    [string]$Lab,
    [ValidateSet("student", "reference")]
    [string]$Mode = "student",
    [ValidateSet("clean", "tampered", "threshold-miss")]
    [string]$Case = "clean",
    [string]$Output
)

$ErrorActionPreference = "Stop"
$env:PYTHONDONTWRITEBYTECODE = "1"
$env:PYTHONUTF8 = "1"
$Root = Split-Path -Parent $PSScriptRoot

if ($env:PYTHON_BIN) {
    $Python = $env:PYTHON_BIN
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    $Python = "python"
} elseif (Get-Command python3 -ErrorAction SilentlyContinue) {
    $Python = "python3"
} else {
    throw "Python 3.10+ was not found. Set PYTHON_BIN."
}

$Arguments = @("$Root\teaching\lab_runner.py", "--lab", $Lab, "--mode", $Mode, "--case", $Case)
if ($Output) {
    $Arguments += @("--output", $Output)
}
& $Python @Arguments
exit $LASTEXITCODE
