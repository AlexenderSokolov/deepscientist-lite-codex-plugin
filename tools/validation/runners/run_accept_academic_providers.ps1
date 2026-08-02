$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$Python = if ($env:PYTHON_BIN) { $env:PYTHON_BIN } else { "python" }
& $Python "$Root\tools\validation\academic_live_provider_acceptance.py" --repo-root $Root @args
exit $LASTEXITCODE
