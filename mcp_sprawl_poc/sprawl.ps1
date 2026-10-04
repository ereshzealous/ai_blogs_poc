# PowerShell shortcut for the portable command `uv run sprawl`. No logic lives here.
uv run --quiet --project $PSScriptRoot sprawl @args
exit $LASTEXITCODE
