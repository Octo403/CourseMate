#Requires -RunAsAdministrator
$ErrorActionPreference = 'Stop'
$serverRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..\..'))
$supervisor = Join-Path $serverRoot 'scripts\run_hosted_server.py'
$hostedDirectory = Join-Path $serverRoot 'data\hosted'
$caddyConfig = Join-Path $serverRoot 'tools\caddy\Caddyfile'
$supervisorPattern = [regex]::Escape($supervisor) + '(?=["\s]|$)'
$hostedPattern = [regex]::Escape($hostedDirectory) + '(?=["\s]|$)'
$caddyPattern = [regex]::Escape($caddyConfig) + '(?=["\s]|$)'
# Windows venv launchers may create children using the base Python executable.
# Identify this deployment by its exact command paths rather than ExecutablePath.
$ownedProcesses = @(Get-CimInstance Win32_Process | Where-Object {
    $_.CommandLine -and (
        ($_.Name -in @('python.exe','pythonw.exe') -and (
            $_.CommandLine -match $supervisorPattern -or
            ($_.CommandLine.Contains('hosted-ui') -and $_.CommandLine -match $hostedPattern)
        )) -or
        ($_.Name -eq 'caddy.exe' -and $_.CommandLine -match $caddyPattern)
    )
})
$task = Get-ScheduledTask -TaskName 'AnotherMe-Hosted-ECS' -ErrorAction SilentlyContinue
if ($task) {
    Disable-ScheduledTask -TaskName 'AnotherMe-Hosted-ECS' | Out-Null
    Stop-ScheduledTask -TaskName 'AnotherMe-Hosted-ECS'
}
# Stop only children belonging to this deployment if Task Scheduler left any behind.
$ownedProcesses | ForEach-Object { Stop-Process -Id $_.ProcessId -ErrorAction SilentlyContinue }
Write-Host 'Task disabled and stopped. To resume: Enable-ScheduledTask and Start-ScheduledTask -TaskName AnotherMe-Hosted-ECS'
