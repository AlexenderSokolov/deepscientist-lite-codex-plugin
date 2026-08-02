param(
    [Parameter(Mandatory=$true)][string]$EvidenceRoot,
    [Parameter(Mandatory=$true)][string]$DbosDependencyRoot,
    [Parameter(Mandatory=$true)][string]$CodexBin,
    [string]$PythonBin = "C:\ProgramData\anaconda3\python.exe",
    [string]$PreviousDecision = "research\.validation-tmp\control-plane-phase2-20260731-03\phase2-decision-02.json",
    [string]$PreviousSmoke = "research\.validation-tmp\control-plane-phase2-20260731-02\canonical-thread-smoke.json"
)
$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
$EvidenceRoot = [IO.Path]::GetFullPath((Join-Path $Root $EvidenceRoot))
$RepoRoot = [IO.Path]::GetFullPath($Root) + [IO.Path]::DirectorySeparatorChar
if (-not $EvidenceRoot.StartsWith($RepoRoot, [StringComparison]::OrdinalIgnoreCase)) { throw "EvidenceRoot must stay inside repository" }
if (Test-Path -LiteralPath $EvidenceRoot) { throw "EvidenceRoot already exists" }
if ((& $PythonBin -c "import platform; print(platform.python_version())") -ne "3.13.5") { throw "Python 3.13.5 required" }
if ((& $CodexBin --version) -ne "codex-cli 0.128.0") { throw "Codex 0.128.0 required" }
if (-not (Test-Path -LiteralPath (Join-Path $DbosDependencyRoot "dbos-2.29.0.dist-info"))) { throw "DBOS 2.29.0 dependency root required" }
$PreviousDecision = [IO.Path]::GetFullPath((Join-Path $Root $PreviousDecision))
$PreviousSmoke = [IO.Path]::GetFullPath((Join-Path $Root $PreviousSmoke))
if ((Get-FileHash $PreviousDecision -Algorithm SHA256).Hash.ToLowerInvariant() -ne "9e3187a2f16e922a6e6360000c914dfabbb57e38695250de9c5be3a5a085372b") { throw "Phase 2 decision-02 hash drift" }
New-Item -ItemType Directory -Path $EvidenceRoot | Out-Null
$env:PYTHONDONTWRITEBYTECODE = "1"
$env:PYTHONPATH = ([IO.Path]::GetFullPath($DbosDependencyRoot)) + ";" + (Join-Path $Root "plugins\deepscientist-lite-core\controller") + $(if ($env:PYTHONPATH) { ";" + $env:PYTHONPATH } else { "" })

& $PythonBin (Join-Path $Root "plugins\deepscientist-lite-core\controller\phase2_fault_harness.py") --workdir (Join-Path $EvidenceRoot "fault-work") --output (Join-Path $EvidenceRoot "fault-matrix.json") --seed 20260731 --trials 100
$faultExit = $LASTEXITCODE
$ErrorActionPreference = "Continue"
& $PythonBin -m unittest tests.test_control_plane_phase2 tests.test_control_plane_phase2_app_server tests.test_control_plane_phase2_broker tests.test_control_plane_phase2_runner tests.test_control_plane_phase2_fault_harness tests.test_control_plane_phase2_evidence tests.test_control_plane_phase1 tests.test_control_plane_phase1_cli tests.test_control_plane_spike -v *> (Join-Path $EvidenceRoot "phase-tests.txt")
$phaseExit = $LASTEXITCODE
$ErrorActionPreference = "Stop"
& $PythonBin -m teaching.control_plane_phase_tests --output (Join-Path $EvidenceRoot "phase0-phase05-tests.json")
$contractExit = $LASTEXITCODE
& $PythonBin teaching\controller_broker_smoke.py --codex-bin $CodexBin --schema-root (Join-Path $Root "plugins\deepscientist-lite-core\schemas\codex\0.128.0") --workspace $Root --runtime (Join-Path $EvidenceRoot "real-runtime") --output (Join-Path $EvidenceRoot "real-fault-broker-smoke.json") --journal-summary (Join-Path $EvidenceRoot "broker-journal-summary.json")
$realExit = $LASTEXITCODE
& $PythonBin -m teaching.control_plane_phase2_evidence managed --project (Join-Path $EvidenceRoot "managed-project") --backup (Join-Path $EvidenceRoot "managed-backup") --restore (Join-Path $EvidenceRoot "managed-restore") --output (Join-Path $EvidenceRoot "managed-probe.json")
$managedExit = $LASTEXITCODE
& $PythonBin -m ds_lite_control doctor --project (Join-Path $EvidenceRoot "managed-project") *> (Join-Path $EvidenceRoot "doctor.txt")
$doctorExit = $LASTEXITCODE
& (Join-Path $Root "run_validate_core.ps1") -Output (Join-Path $EvidenceRoot "core-validation.json")
$coreExit = $LASTEXITCODE
$ErrorActionPreference = "Continue"
& git diff --check *> (Join-Path $EvidenceRoot "git-diff-check.txt")
$diffExit = $LASTEXITCODE
$ErrorActionPreference = "Stop"
& $PythonBin -m teaching.control_plane_phase2_evidence decision --fault (Join-Path $EvidenceRoot "fault-matrix.json") --smoke $PreviousSmoke --managed (Join-Path $EvidenceRoot "managed-probe.json") --tests (Join-Path $EvidenceRoot "phase-tests.txt") --phase-contract (Join-Path $EvidenceRoot "phase0-phase05-tests.json") --core (Join-Path $EvidenceRoot "core-validation.json") --real-broker (Join-Path $EvidenceRoot "real-fault-broker-smoke.json") --broker-journal (Join-Path $EvidenceRoot "broker-journal-summary.json") --previous-decision $PreviousDecision --output (Join-Path $EvidenceRoot "phase2-decision-03.json")
$decisionExit = $LASTEXITCODE
$summary = [ordered]@{ schema_version="ds-lite.phase2-continuation-runner.v1"; fault_exit=$faultExit; phase_tests_exit=$phaseExit; phase_contract_exit=$contractExit; real_broker_exit=$realExit; managed_exit=$managedExit; doctor_exit=$doctorExit; core_exit=$coreExit; diff_exit=$diffExit; decision_exit=$decisionExit; release_allowed=$false }
$summary | ConvertTo-Json -Depth 5 | Set-Content -Encoding utf8 (Join-Path $EvidenceRoot "run-summary.json")
if (@($faultExit,$phaseExit,$contractExit,$realExit,$managedExit,$doctorExit,$coreExit,$diffExit,$decisionExit) -contains 2 -or @($faultExit,$phaseExit,$contractExit,$realExit,$managedExit,$doctorExit,$coreExit,$diffExit,$decisionExit) -contains 1) { exit 2 }
