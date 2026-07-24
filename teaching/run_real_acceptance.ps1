param(
    [Parameter(Mandatory = $true, Position = 0)]
    [ValidateSet("prepare", "preflight", "network", "responses")]
    [string]$Action,

    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Arguments
)

$ErrorActionPreference = "Stop"
$env:PYTHONDONTWRITEBYTECODE = "1"
$env:PYTHONUTF8 = "1"
$PythonBin = if ($env:PYTHON_BIN) { $env:PYTHON_BIN } else { "python" }

& $PythonBin (Join-Path $PSScriptRoot "real_acceptance.py") $Action @Arguments
exit $LASTEXITCODE
