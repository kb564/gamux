# Gamux Bridge Service - Windows Task Scheduler installer
# Run as Administrator:
#   powershell -ExecutionPolicy Bypass -File install-windows-service.ps1

param(
    [string]$PythonPath = "python",
    [string]$ConfigPath = "$PSScriptRoot\config.toml",
    [string]$TaskName = "Gamux-Bridge"
)

$ScriptPath = "$PSScriptRoot\service.py"
$Action = New-ScheduledTaskAction `
    -Execute $PythonPath `
    -Argument "`"$ScriptPath`" --config `"$ConfigPath`""

$Trigger = New-ScheduledTaskTrigger -AtLogOn
$Settings = New-ScheduledTaskSettingsSet `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit ([TimeSpan]::Zero)

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $Action `
    -Trigger $Trigger `
    -Settings $Settings `
    -RunLevel Highest `
    -Force

Write-Host "Gamux Bridge service installed as scheduled task: $TaskName"
Write-Host "To start now: Start-ScheduledTask -TaskName '$TaskName'"
