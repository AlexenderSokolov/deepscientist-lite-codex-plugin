param(
    [Parameter(Mandatory = $true)][string]$Output,
    [Parameter(Mandatory = $true)][string[]]$Evidence,
    [ValidateSet("ds-lite.formal-release-gate.v1", "ds-lite.formal-release-gate.v2")]
    [string]$SchemaVersion = "ds-lite.formal-release-gate.v2"
)
$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$Python = if ($env:PYTHON_BIN) { $env:PYTHON_BIN } else { "python" }
$Arguments = @("$Root\tools\validation\formal_release_gate.py", "--schema-version", $SchemaVersion, "--output", $Output)
foreach ($Item in $Evidence) { $Arguments += @("--evidence", $Item) }
& $Python @Arguments
exit $LASTEXITCODE
