param(
    [ValidateSet("inventory", "check", "diff", "plan-update", "verify")]
    [string]$Command = "verify",
    [string]$Output = ""
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$python = if ($env:PYTHON_BIN) { $env:PYTHON_BIN } else { "python" }
$script = Join-Path $repoRoot "tools\validation\upstream_manager.py"
$args = @($script, $Command, "--repo-root", $repoRoot)
if ($Output) {
    if ($Output.Contains("<") -or $Output.Contains(">")) { throw "output path contains a placeholder" }
    try { $outputPath = [System.IO.Path]::GetFullPath($Output) } catch { throw "output path is invalid" }
    $args += @("--output", $outputPath)
}
& $python @args
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
