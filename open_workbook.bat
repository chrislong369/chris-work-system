@echo off
setlocal
cd /d "%~dp0"
if not exist "exports\Chris_Work_System.xlsx" (
  echo Workbook not found: exports\Chris_Work_System.xlsx
  echo Run python import_chatgpt_updates.py first.
  echo.
  pause
  exit /b 1
)
start "" "%CD%\exports\Chris_Work_System.xlsx"
