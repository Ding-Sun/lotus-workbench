@echo off
chcp 65001 >nul
cd /d "%~dp0.."
echo Two blue/orange boxes will appear. PRESS Win+D while they are on screen.
echo Test runs for 30 seconds.
echo.
".venv\Scripts\python.exe" "tools\desktop_wind_test.py"
echo.
echo ---- report ----
if exist ".tmp\win_d_report.txt" ( type ".tmp\win_d_report.txt" ) else ( echo report missing. )
echo.
pause
