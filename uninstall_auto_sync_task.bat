@echo off
setlocal

set "TASK_NAME=Chris Work System GitHub Sync"
set "PS1=%TEMP%\chris_work_system_uninstall_task.ps1"

> "%PS1%" echo param(
>> "%PS1%" echo     [string]$TaskName
>> "%PS1%" echo ^)
>> "%PS1%" echo $ErrorActionPreference = 'Stop'
>> "%PS1%" echo $existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
>> "%PS1%" echo if ($null -eq $existing) {
>> "%PS1%" echo     Write-Host ('Scheduled task not found: ' + $TaskName)
>> "%PS1%" echo     exit 0
>> "%PS1%" echo }
>> "%PS1%" echo Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
>> "%PS1%" echo Write-Host ('Removed scheduled task: ' + $TaskName)

powershell -NoProfile -ExecutionPolicy Bypass -File "%PS1%" -TaskName "%TASK_NAME%"

if errorlevel 1 (
    echo.
    echo ERROR: Failed to remove scheduled task.
    pause
    exit /b 1
)

echo.
pause
exit /b 0
