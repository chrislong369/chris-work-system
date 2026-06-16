@echo off
setlocal
cd /d "%~dp0"

for /f "usebackq delims=" %%I in (`python backup_project.py`) do set "BACKUP_ZIP=%%I"
if errorlevel 1 (
  echo Backup failed.
  echo.
  pause
  exit /b 1
)

echo Backup created:
echo %BACKUP_ZIP%
echo.
pause
