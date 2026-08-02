# This script deliberately keeps the WSL call as its first executable statement.
wsl.exe -d DS-Lite-Ubuntu-24.04 -- bash -lc 'test "$(uname -s)" = Linux'
$exitCode = $LASTEXITCODE
$output = $args[0]
if ([string]::IsNullOrWhiteSpace($output)) { exit 64 }
if (Test-Path -LiteralPath $output) { exit 65 }
$receipt = [ordered]@{
    schema_version = "ds-lite.wsl-host-probe.v1"
    status = if ($exitCode -eq 0) { "passed" } else { "blocked" }
    host = "windows-powershell"
    distribution = "DS-Lite-Ubuntu-24.04"
    assertion = "uname-s-is-linux"
    exit_code = $exitCode
    raw_output_persisted = $false
}
$receipt | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $output -Encoding utf8 -NoNewline
exit $exitCode
