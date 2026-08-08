$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path
$Python = if ($env:PYTHON_BIN) { $env:PYTHON_BIN } else { "python" }
if (-not $env:IDENTITY_OUTPUT) { throw "IDENTITY_OUTPUT must point to a fresh receipt path" }
$Tag = & $Python -c "import json, pathlib; print(json.loads((pathlib.Path(r'$Root') / 'release' / 'package-set.json').read_text(encoding='utf-8'))['target_tag'])"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $Python (Join-Path $Root "tools\validation\package_identity_receipt.py") --source (Join-Path $Root "plugins\deepscientist-lite-core") --tag $Tag --output $env:IDENTITY_OUTPUT
