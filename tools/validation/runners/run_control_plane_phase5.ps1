param(
    [Parameter(Mandatory=$true)][string]$EvidenceRoot,
    [Parameter(Mandatory=$true)][string]$DbosDependencyRoot,
    [Parameter(Mandatory=$true)][string]$CodexBin,
    [Parameter(Mandatory=$true)][string]$CodexSha256,
    [Parameter(Mandatory=$true)][string]$SchemaRoot,
    [Parameter(Mandatory=$true)][string]$PythonVersion,
    [Parameter(Mandatory=$true)][string]$WindowsPackageRoot,
    [Parameter(Mandatory=$true)][string]$LinuxPackageRoot,
    [Parameter(Mandatory=$true)][string[]]$Receipt,
    [Parameter(Mandatory=$true)][string]$LegacyComplete,
    [Parameter(Mandatory=$true)][string]$Phase4Decision,
    [Parameter(Mandatory=$true)][string]$Phase4DecisionSha256,
    [Parameter(Mandatory=$true)][string]$Regressions,
    [Parameter(Mandatory=$true)][string]$PublicationActions,
    [string]$PythonBin = "C:\ProgramData\anaconda3\python.exe",
    [string]$CodexVersion = "0.146.0"
)

$ErrorActionPreference = "Stop"
$PSNativeCommandUseErrorActionPreference = $false
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
if ([IO.Path]::IsPathRooted($EvidenceRoot)) {
    $EvidenceRoot = [IO.Path]::GetFullPath($EvidenceRoot)
} else {
    $EvidenceRoot = [IO.Path]::GetFullPath((Join-Path $Root $EvidenceRoot))
}
$ResearchPrefix = (Join-Path $Root "research") + [IO.Path]::DirectorySeparatorChar
if (-not $EvidenceRoot.StartsWith($ResearchPrefix, [StringComparison]::OrdinalIgnoreCase)) { throw "EvidenceRoot must stay inside repository research directory" }
if (Test-Path -LiteralPath $EvidenceRoot) { throw "Evidence root already exists" }
if (-not (Test-Path -LiteralPath (Split-Path -Parent $EvidenceRoot) -PathType Container)) { throw "EvidenceRoot parent is missing" }
if ($CodexVersion -ne "0.146.0") { throw "Codex stable 0.146.0 required" }
if (-not (Test-Path -LiteralPath $CodexBin -PathType Leaf)) { throw "Codex binary is missing" }
if (-not (Test-Path -LiteralPath $SchemaRoot -PathType Container)) { throw "Schema root is missing" }
if (-not (Test-Path -LiteralPath $WindowsPackageRoot -PathType Container) -or -not (Test-Path -LiteralPath $LinuxPackageRoot -PathType Container)) { throw "Package roots are missing" }
if (-not (Test-Path -LiteralPath (Join-Path $DbosDependencyRoot "dbos-2.29.0.dist-info") -PathType Container)) { throw "DBOS 2.29.0 required" }
if ((& $PythonBin -c "import platform; print(platform.python_version())") -ne $PythonVersion) { throw "Pinned Python version required" }
if ((& $CodexBin --version) -ne "codex-cli 0.146.0") { throw "Codex stable 0.146.0 required" }
if ((Get-FileHash -LiteralPath $CodexBin -Algorithm SHA256).Hash -ne $CodexSha256) { throw "Codex binary SHA-256 mismatch" }

$RequiredReceipts = @(
    "runtime-windows", "runtime-linux", "resource-windows", "resource-linux",
    "stable-hook", "stable-v2-action", "dbos-upgrade", "supervisor-windows",
    "supervisor-wsl", "real-host-chaos", "network-matrix", "synthetic-provider",
    "fresh-desktop", "openscience", "matched-effect", "backup-restore"
)
$Receipts = @{}
foreach ($Item in $Receipt) {
    $Parts = $Item -split "=", 2
    if ($Parts.Count -ne 2 -or -not $RequiredReceipts.Contains($Parts[0])) { throw "Unsupported receipt input" }
    if ($Receipts.ContainsKey($Parts[0])) { throw "Duplicate receipt input" }
    if (-not (Test-Path -LiteralPath $Parts[1] -PathType Leaf)) { throw "Receipt file is missing: $($Parts[0])" }
    $Receipts[$Parts[0]] = [IO.Path]::GetFullPath($Parts[1])
}
foreach ($Name in $RequiredReceipts) {
    if (-not $Receipts.ContainsKey($Name)) { throw "Missing receipt: $Name" }
}
foreach ($Path in @($Phase4Decision, $LegacyComplete, $Regressions, $PublicationActions)) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw "Final assembly input is missing" }
}
if ((Get-FileHash -LiteralPath $Phase4Decision -Algorithm SHA256).Hash -ne $Phase4DecisionSha256) { throw "Authoritative Phase4 decision SHA-256 mismatch" }
if ((Get-FileHash -LiteralPath $Phase4Decision -Algorithm SHA256).Hash -ne $Phase4DecisionSha256) { throw "Authoritative Phase4 decision SHA-256 mismatch" }

$env:PYTHONDONTWRITEBYTECODE = "1"
$env:PYTHONPATH = ([IO.Path]::GetFullPath($DbosDependencyRoot)) + ";" + (Join-Path $Root "plugins\deepscientist-lite-core\controller") + ";" + $Root
& $PythonBin -c "import sys; from pathlib import Path; from ds_lite_control.runtime_pin import verify_runtime_selection; r=verify_runtime_selection(Path(sys.argv[1]),Path(sys.argv[2]),expected_version=sys.argv[3]); raise SystemExit(0 if r['valid'] else 2)" $CodexBin $SchemaRoot $CodexVersion
if ($LASTEXITCODE -ne 0) { throw "Codex runtime or schema bundle is invalid" }

New-Item -ItemType Directory -Path $EvidenceRoot | Out-Null
$Harness = Join-Path $Root "teaching\control_plane_phase5_final.py"
function Invoke-Harness([string[]]$Arguments) {
    & $PythonBin $Harness @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Phase5 final assembly command failed" }
}

$WindowsManifest = Join-Path $EvidenceRoot "package-windows.json"
$LinuxManifest = Join-Path $EvidenceRoot "package-linux.json"
$Candidate = Join-Path $EvidenceRoot "release-candidate.json"
Invoke-Harness @("package-manifest", "--package-root", $WindowsPackageRoot, "--output", $WindowsManifest)
Invoke-Harness @("package-manifest", "--package-root", $LinuxPackageRoot, "--output", $LinuxManifest)
Invoke-Harness @("candidate", "--repository", $Root, "--windows-package", $WindowsManifest, "--linux-package", $LinuxManifest, "--output", $Candidate)

$GateArguments = @("gate", "--gate-id", "phase5-real-host", "--candidate", $Candidate)
foreach ($Name in $RequiredReceipts) {
    $Original = Join-Path $EvidenceRoot "$Name-original.json"
    $Wrapper = Join-Path $EvidenceRoot "$Name-candidate-evidence.json"
    Copy-Item -LiteralPath $Receipts[$Name] -Destination $Original
    Invoke-Harness @("evidence", "--input-name", $Name, "--candidate", $Candidate, "--original-receipt", $Original, "--output", $Wrapper)
    $GateArguments += @("--input", "$Name=$Wrapper")
}
$GateArguments += @("--output", (Join-Path $EvidenceRoot "phase5-real-host-gate.json"))
Invoke-Harness $GateArguments
$Phase4Original = Join-Path $EvidenceRoot "phase4-decision-original.json"
$Phase4Gate = Join-Path $EvidenceRoot "phase4-real-gate.json"
$Phase5Gate = Join-Path $EvidenceRoot "phase5-real-host-gate.json"
$ControlAggregate = Join-Path $EvidenceRoot "control-aggregate.json"
Copy-Item -LiteralPath $Phase4Decision -Destination $Phase4Original
Invoke-Harness @("gate", "--gate-id", "phase4-real-gate", "--candidate", $Candidate, "--input", "phase4-decision=$Phase4Original", "--phase4-decision-sha256", $Phase4DecisionSha256, "--output", $Phase4Gate)
Invoke-Harness @("aggregate", "--candidate", $Candidate, "--input", "phase4-real-gate=$Phase4Gate", "--input", "phase5-real-host=$Phase5Gate", "--output", $ControlAggregate)
Invoke-Harness @(
    "decision", "--candidate", $Candidate,
    "--input", "legacy-complete=$LegacyComplete",
    "--input", "control-aggregate=$ControlAggregate",
    "--input", "regressions=$Regressions",
    "--input", "publication-actions=$PublicationActions",
    "--input", "phase4-real-gate=$Phase4Gate",
    "--input", "phase5-real-host-gate=$Phase5Gate",
    "--output", (Join-Path $EvidenceRoot "phase5-decision.json")
)
