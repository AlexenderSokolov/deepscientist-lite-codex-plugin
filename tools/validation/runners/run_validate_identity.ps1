$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path
$Python = if ($env:PYTHON_BIN) { $env:PYTHON_BIN } else { "python" }
if (-not $env:IDENTITY_OUTPUT) { throw "IDENTITY_OUTPUT must point to a fresh receipt path" }
& $Python (Join-Path $Root "tools\validation\package_identity_receipt.py") --source (Join-Path $Root "plugins\deepscientist-lite-core") --tag "v0.10.0-beta.2" --output $env:IDENTITY_OUTPUT
