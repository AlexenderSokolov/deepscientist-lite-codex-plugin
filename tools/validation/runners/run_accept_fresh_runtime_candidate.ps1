param(
    [Parameter(Mandatory = $true)][string]$CodexBin,
    [Parameter(Mandatory = $true)][string]$FormalCacheRoot,
    [Parameter(Mandatory = $true)][string]$Workspace,
    [Parameter(Mandatory = $true)][string]$SchemaRoot,
    [Parameter(Mandatory = $true)][string]$Output,
    [Parameter(Mandatory = $true)][string]$CandidateDigest,
    [Parameter(Mandatory = $true)][string]$PackageDigest,
    [Parameter(Mandatory = $true)][string]$ProviderSession
)
$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path
$Python = if ($env:PYTHON_BIN) { $env:PYTHON_BIN } else { "python" }
& $Python "$Root\teaching\fresh_runtime_candidate_acceptance.py" `
    "--codex-bin" $CodexBin "--formal-cache-root" $FormalCacheRoot `
    "--workspace" $Workspace "--schema-root" $SchemaRoot "--output" $Output `
    "--candidate-digest" $CandidateDigest "--package-digest" $PackageDigest `
    "--provider-session" $ProviderSession
exit $LASTEXITCODE
