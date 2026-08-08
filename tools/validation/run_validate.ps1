$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$Candidates = @()
if ($env:PYTHON_BIN) { $Candidates += $env:PYTHON_BIN }
$Candidates += "python3", "python"

foreach ($Python in $Candidates) {
    try {
        & $Python --version *> $null
        if ($LASTEXITCODE -eq 0) {
            & $Python (Join-Path $RepoRoot "tools\validation\validate_all.py") --repo-root $RepoRoot @args
            exit $LASTEXITCODE
        }
    } catch { }
}

throw "Python was not found. Set PYTHON_BIN to a supported interpreter."
