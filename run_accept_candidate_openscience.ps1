$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
$Python = if ($env:PYTHON_BIN) { $env:PYTHON_BIN } else { "python" }
& $Python "$Root\tools\validation\openscience_candidate_acceptance.py" @args
exit $LASTEXITCODE
