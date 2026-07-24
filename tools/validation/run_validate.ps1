$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$TempRoot = if ($env:TEMP_ROOT) { $env:TEMP_ROOT } else { Join-Path $RepoRoot ".validation-tmp" }
$ReceiptId = (Get-Date -Format "yyyyMMddTHHmmssfffffff") + "-" + $PID
$RunTemp = Join-Path $TempRoot ("validation-" + $ReceiptId)
try {
    New-Item -ItemType Directory -Path $RunTemp | Out-Null
} catch {
    Write-Output '{"status":"not-observed","failure_layer":"environment-write","next_action":"set-authorized-temp-root"}'
    exit 2
}
$env:TEMP = $RunTemp
$env:TMP = $RunTemp
$env:PYTHONDONTWRITEBYTECODE = "1"
$env:PYTHONUTF8 = "1"
$env:PYTHONPYCACHEPREFIX = Join-Path $RunTemp "pycache"
if (-not $env:OPENAI_API_KEY) {
    $env:OPENAI_API_KEY = "validation-placeholder"
}
$PythonBin = if ($env:PYTHON_BIN) { $env:PYTHON_BIN } else { "python" }
Set-Location $RepoRoot
$CrossSystemReceipt = Join-Path $RunTemp ("cross-system-validation-" + $ReceiptId + ".json")
$NatureRuntimeReceipt = Join-Path $RunTemp ("nature-runtime-acceptance-" + $ReceiptId + ".json")

& $PythonBin teaching\nature_runtime_acceptance.py --repo-root $RepoRoot --output $NatureRuntimeReceipt
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& $PythonBin -m unittest discover -s tests -v
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& $PythonBin tools\validation\validate_repo.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $PythonBin tools\validation\check_cross_system.py . --output $CrossSystemReceipt
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& powershell.exe -NoProfile -NonInteractive -File (Join-Path $PSScriptRoot "check_powershell_syntax.ps1") -Path (Join-Path $RepoRoot "teaching\run_trusted_hook_host_clean.ps1")
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$CompileTargets = @(
    "plugins/deepscientist-lite/scripts/ds_lite_evidence.py",
    "plugins/deepscientist-lite/scripts/ds_lite_hook.py",
    "plugins/deepscientist-lite/scripts/ds_lite_iteration.py",
    "plugins/deepscientist-lite/scripts/ds_lite_loop.py",
    "plugins/deepscientist-lite/scripts/ds_lite_nature_setup.py",
    "plugins/deepscientist-lite/scripts/codex_autoresearch_adapter.py",
    "plugins/deepscientist-lite/scripts/ds_lite_protocol.py",
    "plugins/deepscientist-lite/scripts/ds_lite_state.py",
    "plugins/deepscientist_lite_import_shim.py",
    "teaching/lab_runner.py",
    "teaching/pilot_runtime.py",
    "teaching/pilot_score.py",
    "teaching/explainability_score.py",
    "teaching/acceptance_gate.py",
    "teaching/transport_diagnostics.py",
    "teaching/fake_transport_codex.py",
    "teaching/offline_acceptance.py",
    "teaching/wire_probe.py",
    "teaching/real_acceptance.py",
    "teaching/matched_effect.py",
    "teaching/host_acceptance.py",
    "teaching/handoff_protocol.py",
    "teaching/cli_compatibility.py",
    "teaching/fresh_host_probe.py",
    "teaching/trusted_host_prepare.py",
    "teaching/trusted_hook_run.py",
    "teaching/nature_runtime_acceptance.py",
    "tools/validation/prepare_codex_acceptance.py",
    "tools/validation/audit_codex_acceptance.py",
    "tools/validation/validate_repo.py",
    "tools/validation/check_text_compatibility.py",
    "tools/validation/check_cross_system.py",
    "tools/validation/upstream_manager.py",
    "tools/validation/generate_nature_adapters.py",
    "tests/test_acceptance_tools.py",
    "tests/test_acceptance_gate.py",
    "tests/test_evidence_pack.py",
    "tests/test_hooks.py",
    "tests/test_iteration.py",
    "tests/test_loop_runner.py",
    "tests/test_offline_loop_acceptance.py",
    "tests/test_loop_integration.py",
    "tests/test_autoresearch_audit.py",
    "tests/test_pilot_runtime.py",
    "tests/test_transport_diagnostics.py",
    "tests/test_offline_acceptance.py",
    "tests/test_real_acceptance.py",
    "tests/test_matched_effect.py",
    "tests/test_host_acceptance.py",
    "tests/test_handoff_protocol.py",
    "tests/test_cli_compatibility.py",
    "tests/test_fresh_host_probe.py",
    "tests/test_protocols.py",
    "tests/test_delegation_probe.py",
    "tests/test_explainability_score.py",
    "tests/test_state_artifact_recovery.py",
    "tests/test_skill_triggers.py",
    "tests/test_state_kernel.py",
    "tests/test_teaching_labs.py",
    "tests/test_upstream_transfer.py",
    "tests/test_text_compatibility.py",
    "tests/test_cross_system.py",
    "tests/test_nature_runtime_acceptance.py"
)
& $PythonBin -m py_compile @CompileTargets
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& git diff --check
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
