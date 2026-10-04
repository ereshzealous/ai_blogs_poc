@echo off
rem Windows shortcut for the portable command `uv run sprawl`. No logic lives here.
uv run --quiet --project "%~dp0." sprawl %*
