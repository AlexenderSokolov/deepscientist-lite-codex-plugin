param(
    [Parameter(Mandatory = $true)] [string]$Path
)
$ErrorActionPreference = "Stop"
if ($ExecutionContext.SessionState.LanguageMode -ne "FullLanguage") {
    Write-Output "powershell syntax not-observed (language mode)"
    exit 0
}
if ($Path -match '<[^>]+>') { throw "placeholder path is not allowed" }
if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw "script path does not exist" }
$tokens = $null
$errors = $null
[System.Management.Automation.Language.Parser]::ParseFile((Resolve-Path -LiteralPath $Path).Path, [ref]$tokens, [ref]$errors) | Out-Null
if ($errors.Count -gt 0) {
    $errors | ForEach-Object { Write-Output ("syntax error at line " + $_.Extent.StartLineNumber) }
    exit 1
}
Write-Output "powershell syntax passed"
