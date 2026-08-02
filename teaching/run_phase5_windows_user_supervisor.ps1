param(
    [Parameter(Mandatory=$true)][string]$TaskName,
    [Parameter(Mandatory=$true)][string]$PythonBin,
    [Parameter(Mandatory=$true)][string]$StateRoot,
    [Parameter(Mandatory=$true)][string]$Witness,
    [Parameter(Mandatory=$true)][string]$Ready,
    [Parameter(Mandatory=$true)][string]$Summary,
    [int]$TimeoutSeconds = 120
)
$ErrorActionPreference = "Stop"
function Get-StringSha256([string]$Value) {
    $Sha = [Security.Cryptography.SHA256]::Create()
    try {
        $Bytes = $Sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($Value))
        return ([BitConverter]::ToString($Bytes)).Replace("-", "").ToLowerInvariant()
    }
    finally { $Sha.Dispose() }
}
function Invoke-ScheduledTaskCommand([string[]]$Arguments) {
    $PreviousPreference = $ErrorActionPreference
    $ErrorActionPreference = "SilentlyContinue"
    try {
        & schtasks.exe @Arguments *> $null
        return $LASTEXITCODE
    }
    finally { $ErrorActionPreference = $PreviousPreference }
}
$RepoRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$StateRoot = [IO.Path]::GetFullPath($StateRoot)
$Witness = [IO.Path]::GetFullPath($Witness)
$Ready = [IO.Path]::GetFullPath($Ready)
$Summary = [IO.Path]::GetFullPath($Summary)
foreach ($Path in @($StateRoot, $Witness, $Ready, $Summary)) {
    if (-not $Path.StartsWith($RepoRoot + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Supervisor evidence paths must stay inside the repository"
    }
}
if (Test-Path -LiteralPath $StateRoot) { throw "StateRoot already exists" }
if (Test-Path -LiteralPath $Witness) { throw "Witness already exists" }
if (Test-Path -LiteralPath $Ready) { throw "Ready already exists" }
if (Test-Path -LiteralPath $Summary) { throw "Summary already exists" }
if ((Invoke-ScheduledTaskCommand @("/Query", "/TN", $TaskName)) -eq 0) {
    throw "TaskName already exists"
}

New-Item -ItemType Directory -Path $StateRoot | Out-Null
$XmlPath = Join-Path $StateRoot "task.xml"
$UserId = "$env:USERDOMAIN\$env:USERNAME"
$WorkerArgs = "-m teaching.control_plane_phase5_supervisor task-supervisor --state-root `"$StateRoot`" --witness `"$Witness`" --ready `"$Ready`" --hold-seconds 180"
$Escape = [Security.SecurityElement]
$Xml = @"
<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo><Description>DS Lite Phase 5 temporary user supervisor acceptance</Description></RegistrationInfo>
  <Principals><Principal id="Author"><UserId>$($Escape::Escape($UserId))</UserId><LogonType>InteractiveToken</LogonType><RunLevel>LeastPrivilege</RunLevel></Principal></Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>false</Hidden>
    <ExecutionTimeLimit>PT5M</ExecutionTimeLimit>
    <Priority>7</Priority>
    <RestartOnFailure><Interval>PT1M</Interval><Count>3</Count></RestartOnFailure>
  </Settings>
  <Actions Context="Author"><Exec><Command>$($Escape::Escape([IO.Path]::GetFullPath($PythonBin)))</Command><Arguments>$($Escape::Escape($WorkerArgs))</Arguments><WorkingDirectory>$($Escape::Escape($RepoRoot))</WorkingDirectory></Exec></Actions>
</Task>
"@
$Xml | Out-File -LiteralPath $XmlPath -Encoding unicode -NoClobber
$Registered = $false
$ReadyObserved = $false
$CleanupObserved = $false
try {
    if ((Invoke-ScheduledTaskCommand @("/Create", "/TN", $TaskName, "/XML", $XmlPath, "/F")) -ne 0) {
        throw "Task Scheduler registration failed"
    }
    $Registered = $true
    if ((Invoke-ScheduledTaskCommand @("/Run", "/TN", $TaskName)) -ne 0) {
        throw "Task Scheduler start failed"
    }
    $Deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while (-not (Test-Path -LiteralPath $Ready) -and (Get-Date) -lt $Deadline) {
        Start-Sleep -Milliseconds 250
    }
    $ReadyObserved = Test-Path -LiteralPath $Ready
    if (-not $ReadyObserved) { throw "Task Scheduler restart did not reach ready" }
}
finally {
    if ($Registered) {
        [void](Invoke-ScheduledTaskCommand @("/End", "/TN", $TaskName))
        [void](Invoke-ScheduledTaskCommand @("/Delete", "/TN", $TaskName, "/F"))
        $CleanupObserved = (Invoke-ScheduledTaskCommand @("/Query", "/TN", $TaskName)) -ne 0
    }
    $Payload = [ordered]@{
        schema_version = "ds-lite.phase5-windows-task-run.v1"
        task_name_sha256 = Get-StringSha256 $TaskName
        registered = $Registered
        ready_observed = $ReadyObserved
        cleanup_observed = $CleanupObserved
        task_xml_sha256 = (Get-FileHash -LiteralPath $XmlPath -Algorithm SHA256).Hash.ToLowerInvariant()
        release_allowed = $false
    }
    $Payload | ConvertTo-Json | Out-File -LiteralPath $Summary -Encoding utf8 -NoClobber
}
if (-not ($Registered -and $ReadyObserved -and $CleanupObserved)) { exit 2 }
