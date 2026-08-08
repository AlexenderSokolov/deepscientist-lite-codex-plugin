param(
    [Parameter(Mandatory=$true)][string]$EvidenceRoot,
    [Parameter(Mandatory=$true)][string]$DbosDependencyRoot,
    [string]$PythonBin = "C:\ProgramData\anaconda3\python.exe"
)
$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path
$EvidenceRoot = [IO.Path]::GetFullPath((Join-Path $Root $EvidenceRoot))
$RepoRoot = [IO.Path]::GetFullPath($Root) + [IO.Path]::DirectorySeparatorChar
if (-not $EvidenceRoot.StartsWith($RepoRoot, [StringComparison]::OrdinalIgnoreCase)) {
    throw "EvidenceRoot must stay inside the repository"
}
if (Test-Path -LiteralPath $EvidenceRoot) { throw "EvidenceRoot already exists" }
if ((& $PythonBin -c "import platform; print(platform.python_version())") -ne "3.13.5") {
    throw "Phase 1 managed verification requires Python 3.13.5"
}
if (-not (Test-Path -LiteralPath (Join-Path $DbosDependencyRoot "dbos-2.29.0.dist-info"))) {
    throw "locked DBOS 2.29.0 dependency root is required"
}
New-Item -ItemType Directory -Path $EvidenceRoot | Out-Null
$env:PYTHONDONTWRITEBYTECODE = "1"
$env:PYTHONPATH = ([IO.Path]::GetFullPath($DbosDependencyRoot)) + ";" + (Join-Path $Root "plugins\deepscientist-lite-control-plane\controller") + $(if ($env:PYTHONPATH) { ";" + $env:PYTHONPATH } else { "" })

& $PythonBin (Join-Path $Root "plugins\deepscientist-lite-core\controller\phase1_fault_harness.py") `
    --dependency-root $DbosDependencyRoot --python-bin $PythonBin `
    --workdir (Join-Path $EvidenceRoot "fault-work") --output (Join-Path $EvidenceRoot "fault-matrix.json") `
    --seed 20260731 --trials 100
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $PythonBin -m teaching.control_plane_phase1_evidence probe `
    --dependency-root $DbosDependencyRoot --python-bin $PythonBin `
    --project (Join-Path $EvidenceRoot "managed-project") --backup (Join-Path $EvidenceRoot "managed-backup") `
    --restore (Join-Path $EvidenceRoot "managed-restore") --output (Join-Path $EvidenceRoot "managed-probe.json")
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $PythonBin -m teaching.control_plane_phase1_evidence tests --python-bin $PythonBin --output (Join-Path $EvidenceRoot "phase-tests.json")
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$env:PYTHON_BIN = $PythonBin
& (Join-Path $PSScriptRoot "run_validate_core.ps1") -Output (Join-Path $EvidenceRoot "core-validation.json")
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $PythonBin -m teaching.control_plane_phase1_evidence decision `
    --fault (Join-Path $EvidenceRoot "fault-matrix.json") --managed (Join-Path $EvidenceRoot "managed-probe.json") `
    --tests (Join-Path $EvidenceRoot "phase-tests.json") --core (Join-Path $EvidenceRoot "core-validation.json") `
    --output (Join-Path $EvidenceRoot "phase1-decision.json")
exit $LASTEXITCODE
