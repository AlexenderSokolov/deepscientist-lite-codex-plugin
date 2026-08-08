$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path
$Python = if ($env:PYTHON_BIN) { $env:PYTHON_BIN } else { "python" }
& $Python (Join-Path $Root "tools\validation\validate_packages.py") --package control-plane
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $Python -m unittest discover -s (Join-Path $Root "tests") -p "test_control_plane*.py" -v
exit $LASTEXITCODE
