param(
    [Parameter(Mandatory=$true)][string]$EvidenceRoot,
    [Parameter(Mandatory=$true)][string]$DbosDependencyRoot,
    [Parameter(Mandatory=$true)][string]$CodexBin,
    [string]$PythonBin = "C:\ProgramData\anaconda3\python.exe",
    [string]$Model = "gpt-5.6-sol",
    [string]$CodexVersion = "0.146.0-alpha.3.1",
    [switch]$AmbientHome
)
$ErrorActionPreference = "Stop"
$PSNativeCommandUseErrorActionPreference = $false
$Root = [IO.Path]::GetFullPath($PSScriptRoot)
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
$Previous = Join-Path $Root "research\.validation-tmp\control-plane-phase2-continuation-20260731-06\phase2-decision-03.json"

& $PythonBin plugins\deepscientist-lite-core\controller\phase3_fault_harness.py --workdir (Join-Path $EvidenceRoot "fault-work") --output (Join-Path $EvidenceRoot "fault-matrix.json") --python-bin $PythonBin --dependency-root $DbosDependencyRoot --seed 20260731 --trials 100 --timeout 20
$faultExit = $LASTEXITCODE
& $PythonBin -m teaching.control_plane_phase3_evidence supervised --project (Join-Path $EvidenceRoot "managed-project") --runtime (Join-Path $EvidenceRoot "managed-runtime") --output (Join-Path $EvidenceRoot "supervised-recovery.json")
$supervisedExit = $LASTEXITCODE
& $PythonBin -m teaching.control_plane_phase3_evidence resource --output (Join-Path $EvidenceRoot "resource-windows.json")
$resourceExit = $LASTEXITCODE
$realArgs = @("teaching\controller_phase3_multigate_smoke.py", "--codex-bin", $CodexBin, "--codex-version", $CodexVersion, "--schema-root", $SchemaRoot, "--task-workspace", (Join-Path $EvidenceRoot "real-workspace"), "--runtime", (Join-Path $EvidenceRoot "real-runtime"), "--output", (Join-Path $EvidenceRoot "real-multigate-smoke.json"), "--journal-summary", (Join-Path $EvidenceRoot "broker-journal-summary.json"), "--model", $Model)
if ($AmbientHome) { $realArgs += "--ambient-home" }
& $PythonBin @realArgs
$realExit = $LASTEXITCODE

$savedErrorActionPreference = $ErrorActionPreference
$ErrorActionPreference = "Continue"
& $PythonBin -m unittest discover -s tests -p "test_control_plane*.py" -v *> (Join-Path $EvidenceRoot "phase-tests.txt")
$testsExit = $LASTEXITCODE
& $PythonBin -m unittest tests.test_hook_in_turn_repair tests.test_controller_broker_worker_lease tests.test_phase3_side_effect_tool -v *> (Join-Path $EvidenceRoot "support-tests.txt")
$supportExit = $LASTEXITCODE
& (Join-Path $Root "run_validate_core.ps1") -Output (Join-Path $EvidenceRoot "core-validation.json")
$coreExit = $LASTEXITCODE
git diff --check *> (Join-Path $EvidenceRoot "git-diff-check.txt")
$diffExit = $LASTEXITCODE
$ErrorActionPreference = $savedErrorActionPreference

$summary = [ordered]@{ schema_version="ds-lite.phase3-runner.v1"; fault_exit=$faultExit; supervised_exit=$supervisedExit; resource_exit=$resourceExit; real_exit=$realExit; tests_exit=$testsExit; support_exit=$supportExit; core_exit=$coreExit; diff_exit=$diffExit; release_allowed=$false }
$summary | ConvertTo-Json | Set-Content -Encoding utf8 (Join-Path $EvidenceRoot "run-summary.json")
& $PythonBin -m teaching.control_plane_phase3_evidence decision --previous $Previous --fault (Join-Path $EvidenceRoot "fault-matrix.json") --real-smoke (Join-Path $EvidenceRoot "real-multigate-smoke.json") --supervised (Join-Path $EvidenceRoot "supervised-recovery.json") --resource (Join-Path $EvidenceRoot "resource-windows.json") --tests (Join-Path $EvidenceRoot "phase-tests.txt") --support-tests (Join-Path $EvidenceRoot "support-tests.txt") --core (Join-Path $EvidenceRoot "core-validation.json") --output (Join-Path $EvidenceRoot "phase3-decision.json")
$decisionExit = $LASTEXITCODE
if ($faultExit -ne 0 -or $supervisedExit -ne 0 -or $resourceExit -ne 0 -or $realExit -ne 0 -or $testsExit -ne 0 -or $supportExit -ne 0 -or $coreExit -ne 0 -or $diffExit -ne 0 -or $decisionExit -ne 0) { exit 2 }
