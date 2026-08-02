param([string]$TempRoot = "")
$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
if (-not $TempRoot) { $TempRoot = if ($env:TEMP_ROOT) { $env:TEMP_ROOT } else { Join-Path $repoRoot "research\.validation-tmp" } }
$receiptId = (Get-Date -Format "yyyyMMddTHHmmssfffffff") + "-" + $PID
$runTemp = Join-Path $TempRoot ("cross-system-" + $receiptId)
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
$receiptPath = Join-Path $runTemp ("cross-system-validation-" + $receiptId + ".json")
& $python (Join-Path $repoRoot "tools\validation\check_cross_system.py") $repoRoot --output $receiptPath
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& powershell.exe -NoProfile -NonInteractive -File (Join-Path $repoRoot "tools\validation\check_powershell_syntax.ps1") -Path (Join-Path $repoRoot "teaching\run_trusted_hook_host_clean.ps1")
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $python -m unittest discover -s (Join-Path $repoRoot "tests") -p "test_cli_compatibility.py" -v
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $python -m unittest discover -s (Join-Path $repoRoot "tests") -p "test_text_compatibility.py" -v
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Output ("cross-system validation completed: " + (Split-Path -Leaf $receiptPath))
