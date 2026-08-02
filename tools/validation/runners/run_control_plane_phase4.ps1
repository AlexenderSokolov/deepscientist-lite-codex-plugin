param(
    [Parameter(Mandatory=$true)][string]$EvidenceRoot,
    [Parameter(Mandatory=$true)][string]$DbosDependencyRoot,
    [Parameter(Mandatory=$true)][string]$CodexBin,
    [string]$PythonBin = "C:\ProgramData\anaconda3\python.exe",
    [string]$Model = "gpt-5.6-sol",
    [string]$CodexVersion = "0.146.0-alpha.3.1"
)
$ErrorActionPreference = "Stop"
$PSNativeCommandUseErrorActionPreference = $false
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$EvidenceRoot = [IO.Path]::GetFullPath((Join-Path $Root $EvidenceRoot))
$RepoPrefix = $Root + [IO.Path]::DirectorySeparatorChar
if (-not $EvidenceRoot.StartsWith($RepoPrefix, [StringComparison]::OrdinalIgnoreCase)) { throw "EvidenceRoot must stay inside repository" }
if (Test-Path -LiteralPath $EvidenceRoot) { throw "EvidenceRoot already exists" }
if ((& $PythonBin -c "import platform; print(platform.python_version())") -ne "3.13.5") { throw "Python 3.13.5 required" }
if ((& $CodexBin --version) -ne "codex-cli $CodexVersion") { throw "Codex $CodexVersion required" }
if (-not (Test-Path -LiteralPath (Join-Path $DbosDependencyRoot "dbos-2.29.0.dist-info"))) { throw "DBOS 2.29.0 required" }
New-Item -ItemType Directory -Path $EvidenceRoot | Out-Null
$env:PYTHONDONTWRITEBYTECODE = "1"
$env:PYTHON_BIN = $PythonBin
$env:PYTHONPATH = ([IO.Path]::GetFullPath($DbosDependencyRoot)) + ";" + (Join-Path $Root "plugins\deepscientist-lite-core\controller") + ";" + $Root
$SchemaRoot = Join-Path $Root "plugins\deepscientist-lite-core\schemas\codex\$CodexVersion"
$Previous = Join-Path $Root "research\.validation-tmp\control-plane-phase3-final-20260731-03\phase3-decision.json"
$PreviousHash = "6fba9ca1417efa3a36faecf45d852b902ddc8a57481dfacc50be112b143a1341"

& $PythonBin -m teaching.control_plane_phase4_evidence verifier-matrix --workdir (Join-Path $EvidenceRoot "verifier-work") --output (Join-Path $EvidenceRoot "verifier-matrix.json")
$verifierExit = $LASTEXITCODE
& $PythonBin teaching\control_plane_phase4_fault_harness.py --workdir (Join-Path $EvidenceRoot "fault-work") --output (Join-Path $EvidenceRoot "reviewer-fault-matrix.json") --python-bin $PythonBin --seed 20260801 --trials 100 --timeout 20
$faultExit = $LASTEXITCODE
& $PythonBin teaching\controller_phase4_reviewer_smoke.py --codex-bin $CodexBin --codex-version $CodexVersion --schema-root $SchemaRoot --runtime (Join-Path $EvidenceRoot "real-runtime") --output (Join-Path $EvidenceRoot "real-reviewer-smoke.json") --journal-summary (Join-Path $EvidenceRoot "broker-journal-summary.json") --aggregate-output (Join-Path $EvidenceRoot "project-release-aggregate.json") --model $Model --ambient-home
$realExit = $LASTEXITCODE
& $PythonBin -m teaching.control_plane_phase4_evidence status-traceability --state-root (Join-Path $EvidenceRoot "real-runtime") --output (Join-Path $EvidenceRoot "status-traceability.json")
$statusExit = $LASTEXITCODE
& $PythonBin -m teaching.control_plane_phase4_evidence backup --state-root (Join-Path $EvidenceRoot "real-runtime") --workdir (Join-Path $EvidenceRoot "backup-work") --output (Join-Path $EvidenceRoot "backup-recovery.json")
$backupExit = $LASTEXITCODE

$savedErrorActionPreference = $ErrorActionPreference
$ErrorActionPreference = "Continue"
& $PythonBin -m unittest discover -s tests -p "test_control_plane*.py" -v *> (Join-Path $EvidenceRoot "phase-tests.txt")
$testsExit = $LASTEXITCODE
& (Join-Path $PSScriptRoot "run_validate_core.ps1") -Output (Join-Path $EvidenceRoot "core-validation.json")
$coreExit = $LASTEXITCODE
git diff --check *> (Join-Path $EvidenceRoot "git-diff-check.txt")
$diffExit = $LASTEXITCODE
$ErrorActionPreference = $savedErrorActionPreference

$summary = [ordered]@{ schema_version="ds-lite.phase4-runner.v1"; verifier_exit=$verifierExit; fault_exit=$faultExit; real_exit=$realExit; status_exit=$statusExit; backup_exit=$backupExit; tests_exit=$testsExit; core_exit=$coreExit; diff_exit=$diffExit; ambient_home=$true; release_allowed=$false }
$summary | ConvertTo-Json | Set-Content -Encoding utf8 (Join-Path $EvidenceRoot "run-summary.json")
& $PythonBin -m teaching.control_plane_phase4_evidence decision --previous $Previous --expected-previous-hash $PreviousHash --verifier (Join-Path $EvidenceRoot "verifier-matrix.json") --fault (Join-Path $EvidenceRoot "reviewer-fault-matrix.json") --real-reviewer (Join-Path $EvidenceRoot "real-reviewer-smoke.json") --status (Join-Path $EvidenceRoot "status-traceability.json") --backup (Join-Path $EvidenceRoot "backup-recovery.json") --aggregate (Join-Path $EvidenceRoot "project-release-aggregate.json") --tests (Join-Path $EvidenceRoot "phase-tests.txt") --core (Join-Path $EvidenceRoot "core-validation.json") --output (Join-Path $EvidenceRoot "phase4-decision.json")
$decisionExit = $LASTEXITCODE
if ($verifierExit -ne 0 -or $faultExit -ne 0 -or $realExit -ne 0 -or $statusExit -ne 0 -or $backupExit -ne 0 -or $testsExit -ne 0 -or $coreExit -ne 0 -or $diffExit -ne 0 -or $decisionExit -ne 0) { exit 2 }
