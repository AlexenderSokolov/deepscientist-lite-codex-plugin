param([string]$Output)
$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
$Python = if ($env:PYTHON_BIN) { $env:PYTHON_BIN } else { "python" }
$Arguments = @("$Root\tools\validation\validate_packages.py", "--repo-root", $Root, "--package", "academic")
if ($Output) { $Arguments += @("--output", $Output) }
& $Python @Arguments
exit $LASTEXITCODE
