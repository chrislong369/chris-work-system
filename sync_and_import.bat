@echo off
setlocal
cd /d "%~dp0"

if /I "%~1"=="/auto" goto auto_sync

python sync_github_inbox.py
set "EXIT_CODE=%ERRORLEVEL%"
echo.
pause
exit /b %EXIT_CODE%

:auto_sync
if not exist "logs" mkdir "logs"
>>"logs\auto_sync.log" echo ============================================================
>>"logs\auto_sync.log" echo [%date% %time%] Starting GitHub inbox sync
python sync_github_inbox.py --auto >>"logs\auto_sync.log" 2>&1
set "EXIT_CODE=%ERRORLEVEL%"
>>"logs\auto_sync.log" echo [%date% %time%] Finished GitHub inbox sync with exit code %EXIT_CODE%
>>"logs\auto_sync.log" echo.
exit /b %EXIT_CODE%
