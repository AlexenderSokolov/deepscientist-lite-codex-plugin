param(
    [ValidateSet("inventory", "doctor", "onboarding", "apply", "verify")]
    [string]$Command = "onboarding",
    [string]$Workspace = "."
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$python = if ($env:PYTHON_BIN) { $env:PYTHON_BIN } else { "python" }
$script = Join-Path $repoRoot "plugins\deepscientist-lite\scripts\ds_lite_nature_setup.py"
if (-not (Test-Path -LiteralPath $script -PathType Leaf)) { throw "nature setup CLI is missing" }
if ($Workspace.Contains("<") -or $Workspace.Contains(">")) { throw "workspace path contains a placeholder" }
$workspacePath = (Resolve-Path -LiteralPath $Workspace).Path
if ($Command -eq "inventory") {
    & $python $script inventory
} else {
    & $python $script $Command --workspace $workspacePath
}
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
