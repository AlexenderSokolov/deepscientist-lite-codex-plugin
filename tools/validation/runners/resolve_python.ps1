param([string]$ExplicitPython = "")

$Candidates = @($ExplicitPython, $env:PYTHON_BIN, "python3", "python") | Where-Object { $_ }
foreach ($Candidate in $Candidates) {
    try {
        & $Candidate --version *> $null
        if ($LASTEXITCODE -eq 0) {
            Write-Output $Candidate
            exit 0
        }
    } catch { }
}

throw "Python was not found. Pass -PythonBin or set PYTHON_BIN."
