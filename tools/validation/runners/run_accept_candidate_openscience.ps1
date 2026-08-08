$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path
$Python = if ($env:PYTHON_BIN) { $env:PYTHON_BIN } else { "python" }
& $Python "$Root\tools\validation\openscience_candidate_acceptance.py" @args
exit $LASTEXITCODE
