param([string]$Output)
$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$Python = if ($env:PYTHON_BIN) { $env:PYTHON_BIN } else { "python" }
$TempRoot = if ($env:TEMP_ROOT) { $env:TEMP_ROOT } else { Join-Path $Root "research\.validation-tmp" }
$RunTemp = Join-Path $TempRoot ("web-validation-" + $PID)
try {
    New-Item -ItemType Directory -Path $RunTemp -Force | Out-Null
} catch {
    Write-Output '{"status":"not-observed","failure_layer":"environment-write","next_action":"set-authorized-temp-root"}'
    exit 2
}
$env:TEMP = $RunTemp
$env:TMP = $RunTemp
$env:PYTHONPYCACHEPREFIX = Join-Path $RunTemp "pycache"
$env:PYTHONDONTWRITEBYTECODE = "1"
& $Python -m unittest discover -s (Join-Path $Root "tests") -p "test_extension_protocols.py" -v
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $Python -m py_compile (Join-Path $Root "plugins\deepscientist-lite-web\scripts\ds_lite_extensions.py")
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$Arguments = @("$Root\tools\validation\validate_packages.py", "--repo-root", $Root, "--package", "web")
if ($Output) { $Arguments += @("--output", $Output) }
& $Python @Arguments
exit $LASTEXITCODE
