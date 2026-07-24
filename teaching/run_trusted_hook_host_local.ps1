param([string]$PilotId = "communication-beta2-20260723-trusted-hook-01")
$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$validationRoot = Join-Path $repoRoot ".validation-tmp"
$pilotRoot = Join-Path $validationRoot $PilotId
if (Test-Path -LiteralPath $pilotRoot) { throw "fresh host already exists; refusing overwrite" }
$codexBin = $env:CODEX_BIN
if (-not $codexBin) { $codexBin = Get-ChildItem -LiteralPath $validationRoot -Recurse -Filter codex.exe -ErrorAction SilentlyContinue | Where-Object { $_.FullName -match "codex-package-0\.144\.5" } | Select-Object -First 1 -ExpandProperty FullName }
if (-not $codexBin -or -not (Test-Path -LiteralPath $codexBin)) { throw "pinned Codex 0.144.5 not found" }
$sourceHome = if ($env:CODEX_SOURCE_HOME) { $env:CODEX_SOURCE_HOME } else { Join-Path $HOME ".codex" }
$python = if ($env:PYTHON_BIN) { $env:PYTHON_BIN } else { "python" }
$env:TEMP = $validationRoot; $env:TMP = $validationRoot; $env:PYTHONUTF8 = "1"; $env:PYTHONDONTWRITEBYTECODE = "1"; $env:PYTHONPATH = $repoRoot
& $python (Join-Path $PSScriptRoot "trusted_host_prepare.py") --codex-bin $codexBin --source-home $sourceHome --repo-root $repoRoot --pilot-root $pilotRoot
if ($LASTEXITCODE -ne 0) { throw "host preparation failed; stopping without retry" }
$homePath = Join-Path $pilotRoot "codex-home"; $workspacePath = Join-Path $pilotRoot "workspace"; $eventsPath = Join-Path $pilotRoot "hook-events"; $outputPath = Join-Path $pilotRoot "hook-host.json"
$env:CODEX_HOME = $homePath; $env:DS_LITE_HOOK_ACCEPTANCE_DIR = $eventsPath
& (Join-Path $PSScriptRoot "run_trusted_hook_host_clean.ps1") -CodexBin $codexBin -CodexHome $homePath -Workspace $workspacePath -HookEvents $eventsPath -Output $outputPath -Prompt "Use shell_command to run the harmless command Write-Output hook-check, then reply done."
exit $LASTEXITCODE
