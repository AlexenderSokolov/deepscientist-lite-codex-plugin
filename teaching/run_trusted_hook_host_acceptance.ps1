param(
    [string]$PilotId = "communication-beta2-20260723-trusted-hook-04",
    [string]$Prompt = "Use apply_patch to edit research/state/graph.json directly, then stop and report the observed decisions.",
    [switch]$TerminalFixture
)
$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$validationRoot = if ($env:TEMP_ROOT) { $env:TEMP_ROOT } else { Join-Path $repoRoot "research\.validation-tmp" }
$null = New-Item -ItemType Directory -Force -Path $validationRoot
$pilotRoot = Join-Path $validationRoot $PilotId
if (Test-Path -LiteralPath $pilotRoot) { throw "fresh host already exists; refusing overwrite" }
$codexBin = $env:CODEX_BIN
if (-not $codexBin) {
    $codexBin = Get-ChildItem -LiteralPath $validationRoot -Recurse -Filter codex.exe -ErrorAction SilentlyContinue |
        Where-Object { $_.FullName -match "codex-package-0\.144\.5" } |
        Select-Object -First 1 -ExpandProperty FullName
}
if (-not $codexBin -or -not (Test-Path -LiteralPath $codexBin)) {
    $requestPath = Join-Path $validationRoot ("user-action-request-" + $PilotId + ".json")
    if (-not (Test-Path -LiteralPath $requestPath)) {
        $request = [ordered]@{
            schema_version = "ds-lite.user-action-request.v1"
            request_id = "uar-$PilotId"
            status = "pending"
            blocking_reason = "trusted Hook host requires a pinned Codex executable"
            required_user_action = "Provide CODEX_BIN, pinned Codex version and SHA-256, then rerun this fresh pilot"
            exact_action = "Set CODEX_BIN to the complete path of the trusted Codex executable"
            allowed_paths = @()
            budget = @{ actions = 1; ttl_minutes = 120 }
            external_boundary = "No provider request or credential transmission until the pinned executable is verified"
            expected_receipt = "hook-host.json"
            expires_at = (Get-Date).ToUniversalTime().AddHours(2).ToString("o")
            forbidden_actions = @("Do not reuse a frozen pilot", "Do not store credentials or raw event streams")
            next_action = "User supplies CODEX_BIN and the pinned executable SHA-256"
            created_at = (Get-Date).ToUniversalTime().ToString("o")
            extensions = @{ scope = "trusted-hook-host" }
        }
        $request | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $requestPath -Encoding utf8 -NoNewline
    }
    @{ status = "not-observed"; failure_layer = "provider-execution"; next_action = "set-CODEX_BIN-and-pinned-version"; user_action_request = $requestPath } | ConvertTo-Json -Compress
    exit 2
}
$sourceHome = if ($env:CODEX_SOURCE_HOME) { $env:CODEX_SOURCE_HOME } else { Join-Path $HOME ".codex" }
$python = if ($env:PYTHON_BIN) { $env:PYTHON_BIN } else { "python" }
$env:TEMP = $validationRoot; $env:TMP = $validationRoot; $env:PYTHONUTF8 = "1"; $env:PYTHONDONTWRITEBYTECODE = "1"; $env:PYTHONPATH = $repoRoot
& $python (Join-Path $PSScriptRoot "trusted_host_prepare.py") --codex-bin $codexBin --source-home $sourceHome --repo-root $repoRoot --pilot-root $pilotRoot
if ($LASTEXITCODE -ne 0) { throw "host preparation failed; stopping without retry" }
$homePath = Join-Path $pilotRoot "codex-home"; $workspacePath = Join-Path $pilotRoot "workspace"; $eventsPath = Join-Path $pilotRoot "hook-events"; $fixtureReceipt = Join-Path $pilotRoot "hook-fixture.json"; $outputPath = Join-Path $pilotRoot "hook-host.json"
$fixtureArgs = @((Join-Path $PSScriptRoot "trusted_hook_fixture.py"), "--workspace", $workspacePath, "--receipt", $fixtureReceipt)
if ($TerminalFixture) { $fixtureArgs += "--terminal" }
& $python @fixtureArgs
if ($LASTEXITCODE -ne 0) { throw "hook fixture preparation failed; stopping without retry" }
$env:CODEX_HOME = $homePath; $env:DS_LITE_HOOK_ACCEPTANCE_DIR = $eventsPath
& (Join-Path $PSScriptRoot "run_trusted_hook_host_clean.ps1") -CodexBin $codexBin -CodexHome $homePath -Workspace $workspacePath -HookEvents $eventsPath -Output $outputPath -Prompt $Prompt
$exitCode = $LASTEXITCODE
if ($exitCode -ne 0) {
    $requestDir = Join-Path $workspacePath "research\artifacts"
    $requestPath = Join-Path $requestDir ("user-action-request-" + $PilotId + ".json")
    if (-not (Test-Path -LiteralPath $requestPath)) {
        $null = New-Item -ItemType Directory -Force -Path $requestDir
        $request = [ordered]@{
            schema_version = "ds-lite.user-action-request.v1"
            request_id = "uar-$PilotId"
            status = "pending"
            blocking_reason = "fresh trusted Hook host did not complete the Codex task"
            required_user_action = "Authorize or repair the configured provider/auth route, then rerun a new pilot"
            exact_action = "Inspect hook-host.json and the redacted diagnostic receipt; provide the provider trust/auth receipt"
            allowed_paths = @("research/artifacts")
            budget = @{ actions = 1; ttl_minutes = 120 }
            external_boundary = "No retry, credential capture, or provider bypass is permitted"
            expected_receipt = "hook-host.json"
            expires_at = (Get-Date).ToUniversalTime().AddHours(2).ToString("o")
            forbidden_actions = @("Do not reuse this pilot", "Do not store credentials or raw event streams")
            next_action = "Resolve the provider/auth failure and submit the resulting receipt"
            created_at = (Get-Date).ToUniversalTime().ToString("o")
            extensions = @{ scope = "trusted-hook-host"; failure_receipt = "hook-host.json" }
        }
        $request | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $requestPath -Encoding utf8 -NoNewline
    }
}
exit $exitCode
