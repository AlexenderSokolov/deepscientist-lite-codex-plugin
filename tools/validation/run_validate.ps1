$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$TempRoot = if ($env:TEMP_ROOT) { $env:TEMP_ROOT } else { Join-Path $RepoRoot "research\.validation-tmp" }
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

& $PythonBin tests/run_unittest.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& $PythonBin tools\validation\validate_repo.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $PythonBin tools\validation\validate_packages.py --repo-root $RepoRoot --package all
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
    "plugins/deepscientist-lite-core/scripts/ds_lite_evidence.py",
    "plugins/deepscientist-lite-core/scripts/ds_lite_hook.py",
    "plugins/deepscientist-lite-core/scripts/ds_lite_handoff.py",
    "plugins/deepscientist-lite-core/scripts/ds_lite_iteration.py",
    "plugins/deepscientist-lite-core/scripts/ds_lite_loop.py",
    "plugins/deepscientist-lite-core/scripts/ds_lite_autoresearch_runner.py",
    "plugins/deepscientist-lite-core/scripts/ds_lite_protocol.py",
    "plugins/deepscientist-lite-core/scripts/ds_lite_state.py",
    "plugins/deepscientist-lite-core/scripts/ds_lite_learning.py",
    "plugins/deepscientist-lite-core/scripts/ds_lite_quality.py",
    "plugins/deepscientist-lite-academic/scripts/ds_lite_nature_setup.py",
    "plugins/deepscientist-lite-academic/scripts/ds_lite_pack_doctor.py",
    "plugins/deepscientist-lite-academic/scripts/ds_lite_citation_check.py",
    "plugins/deepscientist-lite-academic/scripts/ds_lite_revision_guard.py",
    "plugins/deepscientist-lite-web/scripts/ds_lite_extensions.py",
    "tools/validation/acquire_pinned_codex.py",
    "plugins/deepscientist-lite-knowledge/scripts/ds_lite_knowledge.py",
    "plugins/deepscientist-lite-knowledge/scripts/ds_lite_pack_doctor.py",
    "plugins/deepscientist-lite-empirical/scripts/ds_lite_empirical.py",
    "plugins/deepscientist-lite-engineering/scripts/ds_lite_engineering.py",
    "tools/validation/release_receipt.py",
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
    "teaching/app_server_continuation_acceptance.py",
    "teaching/memory_diagnostic.py",
    "teaching/rust_transport_probe.py",
    "teaching/trusted_host_prepare.py",
    "teaching/trusted_hook_run.py",
    "teaching/nature_runtime_acceptance.py",
    "tools/validation/prepare_codex_acceptance.py",
    "tools/validation/audit_codex_acceptance.py",
    "tools/validation/validate_repo.py",
    "tools/validation/validate_packages.py",
    "tools/validation/formal_release_gate.py",
    "tools/validation/academic_live_provider_acceptance.py",
    "tools/validation/audit_superpowers.py",
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
    "tests/test_rust_transport_probe.py",
    "tests/test_app_server_continuation_acceptance.py",
    "tests/test_memory_diagnostic.py",
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
    "tests/test_nature_runtime_acceptance.py",
    "tests/test_extension_protocols.py",
    "tests/test_plugin_packages.py",
    "tests/test_academic_protocols.py",
    "tests/test_empirical_pack.py",
    "tests/test_engineering_pack.py",
    "tests/test_cross_disciplinary_adoption.py",
    "tests/test_superpowers_compatibility.py",
    "tests/test_learning_protocol.py",
    "tests/test_quality_protocol.py"
)
& $PythonBin -m py_compile @CompileTargets
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& git diff --check
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
