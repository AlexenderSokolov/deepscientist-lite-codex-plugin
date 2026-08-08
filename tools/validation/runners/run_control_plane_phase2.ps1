param(
    [Parameter(Mandatory=$true)][string]$EvidenceRoot,
    [Parameter(Mandatory=$true)][string]$DbosDependencyRoot,
    [string]$PythonBin = "",
    [string]$CodexBin = ""
)
$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path
$PythonBin = & (Join-Path $PSScriptRoot "resolve_python.ps1") -ExplicitPython $PythonBin
if (-not $CodexBin) { $CodexBin = $env:CODEX_BIN }
if (-not $CodexBin) { $CodexBin = (Get-Command codex -ErrorAction Stop).Source }
$EvidenceRoot = [IO.Path]::GetFullPath((Join-Path $Root $EvidenceRoot))
$RepoRoot = [IO.Path]::GetFullPath($Root) + [IO.Path]::DirectorySeparatorChar
if (-not $EvidenceRoot.StartsWith($RepoRoot, [StringComparison]::OrdinalIgnoreCase)) { throw "EvidenceRoot must stay inside repository" }
if (Test-Path -LiteralPath $EvidenceRoot) { throw "EvidenceRoot already exists" }
if ((& $PythonBin -c "import platform; print(platform.python_version())") -ne "3.13.5") { throw "Python 3.13.5 required" }
if (-not (Test-Path -LiteralPath (Join-Path $DbosDependencyRoot "dbos-2.29.0.dist-info"))) { throw "DBOS 2.29.0 dependency root required" }
if (-not (Test-Path -LiteralPath $CodexBin)) { throw "pinned Codex app-server binary required" }
New-Item -ItemType Directory -Path $EvidenceRoot | Out-Null
$env:PYTHONDONTWRITEBYTECODE = "1"
$env:PYTHONPATH = ([IO.Path]::GetFullPath($DbosDependencyRoot)) + ";" + (Join-Path $Root "plugins\deepscientist-lite-control-plane\controller") + $(if ($env:PYTHONPATH) { ";" + $env:PYTHONPATH } else { "" })
& $PythonBin (Join-Path $Root "plugins\deepscientist-lite-control-plane\controller\phase2_fault_harness.py") --workdir (Join-Path $EvidenceRoot "fault-work") --output (Join-Path $EvidenceRoot "fault-matrix.json") --seed 20260731 --trials 100
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $PythonBin -m unittest tests.test_control_plane_phase2 tests.test_control_plane_phase2_app_server tests.test_control_plane_phase2_runner tests.test_control_plane_phase2_fault_harness tests.test_control_plane_phase1 tests.test_control_plane_phase1_cli -v *> (Join-Path $EvidenceRoot "phase-tests.txt")
$phaseExit = $LASTEXITCODE
& $PythonBin teaching\controller_app_server_smoke.py --codex-bin $CodexBin --home (Join-Path $EvidenceRoot "codex-home") --workspace $Root --schema-root (Join-Path $Root "plugins\deepscientist-lite-control-plane\schemas\codex\0.128.0") --output (Join-Path $EvidenceRoot "canonical-thread-smoke.json")
$smokeExit = $LASTEXITCODE
& $PythonBin -m teaching.control_plane_phase2_evidence managed --project (Join-Path $EvidenceRoot "managed-project") --backup (Join-Path $EvidenceRoot "managed-backup") --restore (Join-Path $EvidenceRoot "managed-restore") --output (Join-Path $EvidenceRoot "managed-probe.json")
$managedExit = $LASTEXITCODE
& $PythonBin -m ds_lite_control doctor --project (Join-Path $EvidenceRoot "managed-project") *> (Join-Path $EvidenceRoot "doctor.txt")
$doctorExit = $LASTEXITCODE
& (Join-Path $PSScriptRoot "run_validate_core.ps1") -Output (Join-Path $EvidenceRoot "core-validation.json")
$coreExit = $LASTEXITCODE
& $PythonBin -c "import ast; from pathlib import Path; files=list(Path(r'$Root\plugins\deepscientist-lite-control-plane\controller\ds_lite_control').glob('*.py')); [ast.parse(p.read_text(encoding='utf-8'), filename=str(p)) for p in files]; print('AST_OK', len(files))"
$compileExit = $LASTEXITCODE
$summary = [ordered]@{ schema_version="ds-lite.phase2-runner.v1"; phase="2"; fault_matrix=(Join-Path $EvidenceRoot "fault-matrix.json"); phase_tests_exit=$phaseExit; canonical_smoke_exit=$smokeExit; managed_exit=$managedExit; doctor_exit=$doctorExit; core_exit=$coreExit; compile_exit=$compileExit; release_allowed=$false }
$summary | ConvertTo-Json -Depth 5 | Set-Content -Encoding utf8 (Join-Path $EvidenceRoot "run-summary.json")
& $PythonBin -m teaching.control_plane_phase2_evidence decision --fault (Join-Path $EvidenceRoot "fault-matrix.json") --smoke (Join-Path $EvidenceRoot "canonical-thread-smoke.json") --managed (Join-Path $EvidenceRoot "managed-probe.json") --tests (Join-Path $EvidenceRoot "phase-tests.txt") --core (Join-Path $EvidenceRoot "core-validation.json") --output (Join-Path $EvidenceRoot "phase2-decision.json")
if ($phaseExit -ne 0 -or $smokeExit -ne 0 -or $managedExit -ne 0 -or $doctorExit -ne 0 -or $coreExit -ne 0 -or $compileExit -ne 0) { exit 2 }
