@echo off
setlocal

set "TASK_NAME=Chris Work System GitHub Sync"
cd /d "%~dp0"
set "PROJECT_DIR=%CD%"
set "SYNC_BAT=%PROJECT_DIR%\sync_and_import.bat"
set "LOG_DIR=%PROJECT_DIR%\logs"
set "PS1=%TEMP%\chris_work_system_install_task.ps1"

if not exist "%SYNC_BAT%" (
    echo ERROR: Cannot find "%SYNC_BAT%".
    echo Run this installer from the Chris Work System project folder.
    pause
    exit /b 1
)

if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

> "%PS1%" echo param(
>> "%PS1%" echo     [string]$TaskName,
>> "%PS1%" echo     [string]$ProjectDir,
>> "%PS1%" echo     [string]$SyncBat
>> "%PS1%" echo ^)
>> "%PS1%" echo $ErrorActionPreference = 'Stop'
>> "%PS1%" echo $currentUser = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
>> "%PS1%" echo $existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
>> "%PS1%" echo if ($null -ne $existing) {
>> "%PS1%" echo     Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
>> "%PS1%" echo }
>> "%PS1%" echo $action = New-ScheduledTaskAction -Execute $SyncBat -Argument '/auto' -WorkingDirectory $ProjectDir
>> "%PS1%" echo $logon = New-ScheduledTaskTrigger -AtLogOn
>> "%PS1%" echo $logon.UserId = $currentUser
>> "%PS1%" echo $repeat = (New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 15) -RepetitionDuration (New-TimeSpan -Days 3650)).Repetition
>> "%PS1%" echo $logon.Repetition = $repeat
>> "%PS1%" echo $principal = New-ScheduledTaskPrincipal -UserId $currentUser -LogonType Interactive -RunLevel Limited
>> "%PS1%" echo $settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 30) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable
>> "%PS1%" echo Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $logon -Principal $principal -Settings $settings -Description 'Automatically syncs the Chris Work System GitHub inbox at logon and every 15 minutes while the user is logged in.' -Force ^| Out-Null
>> "%PS1%" echo Write-Host ('Installed scheduled task: ' + $TaskName)
>> "%PS1%" echo Write-Host ('Runs: ' + $SyncBat + ' /auto')
>> "%PS1%" echo Write-Host 'Schedule: at user logon, then every 15 minutes while logged in.'

powershell -NoProfile -ExecutionPolicy Bypass -File "%PS1%" -TaskName "%TASK_NAME%" -ProjectDir "%PROJECT_DIR%" -SyncBat "%SYNC_BAT%"

if errorlevel 1 (
    echo.
    echo ERROR: Failed to install scheduled task.
    pause
    exit /b 1
)

echo.
echo Log file:
echo "%LOG_DIR%\auto_sync.log"
echo.
pause
exit /b 0
