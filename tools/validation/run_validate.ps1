$ErrorActionPreference = "Stop"
$env:PYTHONDONTWRITEBYTECODE = "1"
$PythonBin = if ($env:PYTHON_BIN) { $env:PYTHON_BIN } else { "python" }

& $PythonBin -m unittest discover -s tests -v
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& $PythonBin tools\validation\validate_repo.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& $PythonBin -m py_compile `
  plugins\deepscientist-lite\scripts\ds_lite_state.py `
  tools\validation\validate_repo.py `
  tests\test_state_kernel.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
