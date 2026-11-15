@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo [Lotus] .venv not found. Create it with:
    echo   python -m venv .venv
    exit /b 1
)
".venv\Scripts\python.exe" -m app %*
