param(
    [string]$Output = ""
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$python = if ($env:PYTHON_BIN) { $env:PYTHON_BIN } else { "python" }
$script = Join-Path $repoRoot "teaching\nature_runtime_acceptance.py"
if (-not (Test-Path -LiteralPath $script -PathType Leaf)) {
    throw "nature runtime acceptance CLI is missing"
}
if ($Output.Contains("<") -or $Output.Contains(">")) {
    throw "output path contains a placeholder"
}
if (-not $Output) {
    $runId = (Get-Date -Format "yyyyMMddTHHmmssfffffff") + "-" + $PID
    $baseRoot = if ($env:TEMP_ROOT) { $env:TEMP_ROOT } else { Join-Path $repoRoot "research\.validation-tmp" }
    $outputRoot = Join-Path $baseRoot "nature-runtime-$runId"
    New-Item -ItemType Directory -Path $outputRoot | Out-Null
    $Output = Join-Path $outputRoot "receipt.json"
}
& $python $script --repo-root $repoRoot --output $Output
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
