@echo off
chcp 65001 >nul
cd /d "%~dp0.."
echo Running desktop layer check. A blue test window will appear for ~9 seconds.
echo.
".venv\Scripts\python.exe" "tools\desktop_layer_check.py"
echo.
echo ---- report ----
if exist ".tmp\desktop_layer_report.txt" (
    type ".tmp\desktop_layer_report.txt"
) else (
    echo report missing - the script failed before writing it.
)
echo.
pause
