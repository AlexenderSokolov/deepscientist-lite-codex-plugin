param([switch]$$Resume)

$$ErrorActionPreference = "Stop"
$$Root = Split-Path -Parent $$MyInvocation.MyCommand.Path
$$Python = if ($$env:PYTHON_BIN) { $$env:PYTHON_BIN } else { "python" }
$$Cli = if ($$env:DS_LITE_AUTONOMY_CLI) {
    $$env:DS_LITE_AUTONOMY_CLI
} elseif ($$env:DS_LITE_PLUGIN_ROOT) {
    Join-Path $$env:DS_LITE_PLUGIN_ROOT "scripts\ds_lite_autonomy.py"
} else {
    throw "Set DS_LITE_AUTONOMY_CLI or DS_LITE_PLUGIN_ROOT before running this script."
}
if (-not (Test-Path -LiteralPath $$Cli -PathType Leaf)) {
    throw "DS Lite autonomy CLI does not exist."
}
$$Contract = Join-Path $$Root "research\\autonomy\\contract.json"
$$Output = Join-Path $$Root "research\\autonomy\\run"
$$Args = @("--root", $$Root, "--contract", $$Contract, "--output", $$Output)
if ($$Resume) { $$Args += "--resume" }
& $$Python $$Cli @Args
exit $$LASTEXITCODE
