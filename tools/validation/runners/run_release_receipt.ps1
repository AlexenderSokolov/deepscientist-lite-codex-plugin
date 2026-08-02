param(
    [Parameter(Mandatory = $true)][string]$Tag,
    [Parameter(Mandatory = $true)][string]$Marketplace,
    [Parameter(Mandatory = $true)][string[]]$Cache,
    [Parameter(Mandatory = $true)][string]$Output
)
$ErrorActionPreference = "Stop"
$Python = if ($env:PYTHON_BIN) { $env:PYTHON_BIN } else { "python" }
$Arguments = @((Join-Path $PSScriptRoot "..\release_receipt.py"), "--tag", $Tag, "--marketplace", $Marketplace, "--output", $Output)
foreach ($Item in $Cache) { $Arguments += @("--cache", $Item) }
& $Python @Arguments
exit $LASTEXITCODE
