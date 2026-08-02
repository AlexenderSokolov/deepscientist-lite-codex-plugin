$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$TempRoot = if ($env:TEMP_ROOT) { $env:TEMP_ROOT } else { Join-Path $RepoRoot "research\.validation-tmp" }
$RunId = (Get-Date -Format "yyyyMMddTHHmmssfffffff") + "-" + $PID
$RunTemp = Join-Path $TempRoot ("tests-" + $RunId)
New-Item -ItemType Directory -Path $RunTemp | Out-Null

# Keep every Python temporary file and bytecode cache on the project volume.
$env:TEMP = $RunTemp
$env:TMP = $RunTemp
$env:TEMP_ROOT = $RunTemp
$env:DS_LITE_TEST_ROOT = $RunTemp
$env:PYTHONDONTWRITEBYTECODE = "1"
$env:PYTHONUTF8 = "1"
$env:PYTHONPYCACHEPREFIX = Join-Path $RunTemp "pycache"
$PythonBin = if ($env:PYTHON_BIN) { $env:PYTHON_BIN } else { "python" }
Set-Location $RepoRoot
& $PythonBin tests/run_unittest.py
exit $LASTEXITCODE
