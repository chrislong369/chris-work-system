@echo off
setlocal
cd /d "%~dp0"
python import_chatgpt_updates.py
echo.
pause
