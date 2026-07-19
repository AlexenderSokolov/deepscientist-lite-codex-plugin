$ErrorActionPreference = "Stop"
$env:PYTHONDONTWRITEBYTECODE = "1"
$env:PYTHONUTF8 = "1"
$PythonBin = if ($env:PYTHON_BIN) { $env:PYTHON_BIN } else { "python" }

& $PythonBin -m unittest discover -s tests -v
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& $PythonBin tools\validation\validate_repo.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& $PythonBin -m py_compile `
  plugins\deepscientist-lite\scripts\ds_lite_evidence.py `
  plugins\deepscientist-lite\scripts\ds_lite_protocol.py `
  plugins\deepscientist-lite\scripts\ds_lite_state.py `
  teaching\lab_runner.py `
  tools\validation\prepare_codex_acceptance.py `
  tools\validation\audit_codex_acceptance.py `
  tools\validation\validate_repo.py `
  tools\validation\audit_upstream_adoption.py `
  plugins\deepscientist-lite\scripts\ds_lite_communication_audit.py `
  plugins\deepscientist-lite\scripts\ds_lite_hook.py `
  tests\test_acceptance_tools.py `
  tests\test_evidence_pack.py `
  tests\test_protocols.py `
  tests\test_state_kernel.py `
  tests\test_teaching_labs.py `
  tests\test_communication_layer.py `
  tests\test_communication_audit.py `
  tests\test_communication_hook.py `
  tests\test_upstream_adoption.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
