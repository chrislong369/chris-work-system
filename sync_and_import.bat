@echo off
setlocal
cd /d "%~dp0"
python sync_github_inbox.py
echo.
pause
