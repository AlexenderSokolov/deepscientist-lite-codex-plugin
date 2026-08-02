param([string]$TempRoot = "")
$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
if (-not $TempRoot) { $TempRoot = if ($env:TEMP_ROOT) { $env:TEMP_ROOT } else { Join-Path $repoRoot "research\.validation-tmp" } }
$runId = (Get-Date -Format "yyyyMMddTHHmmssfffffff") + "-" + $PID
$runTemp = Join-Path $TempRoot ("loop-acceptance-" + $runId)
try {
    New-Item -ItemType Directory -Path $runTemp | Out-Null
} catch {
    Write-Output '{"status":"not-observed","failure_layer":"environment-write","next_action":"set-authorized-temp-root"}'
    exit 2
}
$env:TEMP = $runTemp
$env:TMP = $runTemp
$env:PYTHONUTF8 = "1"
$env:PYTHONDONTWRITEBYTECODE = "1"
$env:PYTHONPYCACHEPREFIX = Join-Path $runTemp "pycache"
$python = if ($env:PYTHON_BIN) { $env:PYTHON_BIN } else { "python" }
$loopCli = Join-Path $repoRoot "plugins\deepscientist-lite-core\scripts\ds_lite_loop.py"
$loopTests = Join-Path $repoRoot "tests\test_loop_runner.py"
$offlineCli = Join-Path $repoRoot "teaching\offline_loop_acceptance.py"

& $python $offlineCli --output (Join-Path $runTemp "offline-loop")
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& $python -m unittest discover -s (Join-Path $repoRoot "tests") -p "test_loop_runner.py" -v
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $python $loopCli --help | Out-Null
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $python -m py_compile $loopCli $loopTests
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Output '{"status":"passed","adapter":"fake","test_suite":"test_loop_runner.py","external_request_observed":false}'
