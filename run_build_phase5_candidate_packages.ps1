param(
    [Parameter(Mandatory=$true)][string]$WindowsPackageRoot,
    [Parameter(Mandatory=$true)][string]$LinuxPackageRoot,
    [Parameter(Mandatory=$true)][string]$EvidenceRoot,
    [string]$PythonBin = "C:\ProgramData\anaconda3\python.exe"
)

$ErrorActionPreference = "Stop"
$Root = [IO.Path]::GetFullPath($PSScriptRoot)
$WindowsPackageRoot = [IO.Path]::GetFullPath($WindowsPackageRoot)
$LinuxPackageRoot = [IO.Path]::GetFullPath($LinuxPackageRoot)
$EvidenceRoot = [IO.Path]::GetFullPath($EvidenceRoot)
foreach ($Path in @($WindowsPackageRoot, $LinuxPackageRoot, $EvidenceRoot)) {
    if (Test-Path -LiteralPath $Path) { throw "Phase 5 package output already exists" }
}
New-Item -ItemType Directory -Path $EvidenceRoot | Out-Null
$Builder = Join-Path $Root "tools\validation\phase5_release_package_builder.py"
& $PythonBin $Builder --repository $Root --output-root $WindowsPackageRoot --receipt (Join-Path $EvidenceRoot "windows-package-build.json")
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $PythonBin $Builder --repository $Root --output-root $LinuxPackageRoot --receipt (Join-Path $EvidenceRoot "linux-package-build.json")
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$Windows = Get-Content -LiteralPath (Join-Path $EvidenceRoot "windows-package-build.json") -Raw | ConvertFrom-Json
$Linux = Get-Content -LiteralPath (Join-Path $EvidenceRoot "linux-package-build.json") -Raw | ConvertFrom-Json
if ($Windows.package_digest -ne $Linux.package_digest) { throw "Platform package digests differ" }
Write-Output ("package_digest=" + $Windows.package_digest)
