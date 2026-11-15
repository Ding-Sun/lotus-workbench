@echo off
rem Double-click launcher. Starts Lotus with no console window and exits.
cd /d "%~dp0"
start "" ".venv\Scripts\pythonw.exe" -m app
exit /b 0
