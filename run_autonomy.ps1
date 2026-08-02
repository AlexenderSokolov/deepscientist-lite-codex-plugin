param(
    [Parameter(Mandatory = $true)][string]$Root,
    [Parameter(Mandatory = $true)][string]$Contract,
    [Parameter(Mandatory = $true)][string]$Output
)
$ErrorActionPreference = "Stop"
$Python = if ($env:PYTHON_BIN) { $env:PYTHON_BIN } else { "python" }
& $Python "$PSScriptRoot\plugins\deepscientist-lite-core\scripts\ds_lite_autonomy.py" --root $Root --contract $Contract --output $Output
exit $LASTEXITCODE
