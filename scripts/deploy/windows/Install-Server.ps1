#Requires -RunAsAdministrator
param([Parameter(Mandatory=$true)][string]$PublicIp)

$ErrorActionPreference = 'Stop'
$serverRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..\..'))
Set-Location -LiteralPath $serverRoot
$serverIp = [Net.IPAddress]::Parse($PublicIp)
if ($serverIp.AddressFamily -ne [Net.Sockets.AddressFamily]::InterNetwork) {
    throw 'Provide the ECS public IPv4 address.'
}
$PublicIp = $serverIp.ToString()
$env:PYTHONUTF8 = '1'

if (Get-ScheduledTask -TaskName 'AnotherMe-Hosted-ECS' -ErrorAction SilentlyContinue) {
    Write-Host 'Stopping the existing deployment before updating its Python environment...'
    & (Join-Path $PSScriptRoot 'Stop-Server.ps1')
}

Write-Host 'Creating the Python environment (install 64-bit Python 3.13 first)...'
if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
    & py -3.13 -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Python environment creation failed.' }
}
$serverPython = Join-Path $serverRoot '.venv\Scripts\python.exe'
& $serverPython -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw 'pip upgrade failed. Check Internet access.' }
& $serverPython -m pip install -e '.[question-bank]'
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
& $serverPython -c "import aitown.ui.hosted; print('Hosted source:', aitown.ui.hosted.__file__)"
if ($LASTEXITCODE -ne 0) { throw 'The hosted application could not be imported.' }

$caddyDirectory = Join-Path $serverRoot 'tools\caddy'
New-Item -ItemType Directory -Force -Path $caddyDirectory | Out-Null
$serverCaddy = Join-Path $caddyDirectory 'caddy.exe'
if (-not (Test-Path -LiteralPath $serverCaddy)) {
    Write-Host 'Downloading the standard Windows x64 Caddy build...'
    Invoke-WebRequest -UseBasicParsing -Uri 'https://caddyserver.com/api/download?os=windows&arch=amd64' -OutFile $serverCaddy
}

$caddyData = Join-Path $serverRoot 'data\caddy'
New-Item -ItemType Directory -Force -Path $caddyData | Out-Null
$caddyConfig = Join-Path $caddyDirectory 'Caddyfile'
if (-not (Test-Path -LiteralPath $caddyConfig)) {
    Write-Host 'Choose a site access password for teachers/students. Username: class'
    Write-Host 'Caddy will prompt for the password; it is not saved as plaintext.'
    $sitePasswordHash = & $serverCaddy hash-password
    if ($LASTEXITCODE -ne 0 -or -not $sitePasswordHash) { throw 'Password setup failed.' }
    $template = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'Caddyfile.template') -Raw
    $config = $template.Replace('__PUBLIC_IP__', $PublicIp).Replace('__DATA_DIR__', $caddyData.Replace('\','/')).Replace('__PASSWORD_HASH__', $sitePasswordHash.Trim())
    [IO.File]::WriteAllText($caddyConfig, $config, (New-Object Text.UTF8Encoding($false)))
}
& $serverCaddy validate --config $caddyConfig --adapter caddyfile
if ($LASTEXITCODE -ne 0) { throw 'Caddy configuration is invalid.' }

foreach ($serverPort in @(80,443)) {
    $ruleName = 'AnotherMe-Web-' + $serverPort
    if (-not (Get-NetFirewallRule -Name $ruleName -ErrorAction SilentlyContinue)) {
        New-NetFirewallRule -Name $ruleName -DisplayName $ruleName -Direction Inbound -Action Allow -Protocol TCP -LocalPort $serverPort -Program $serverCaddy | Out-Null
    }
}

$supervisor = Join-Path $serverRoot 'scripts\run_hosted_server.py'
$action = New-ScheduledTaskAction -Execute $serverPython -Argument ('-u "' + $supervisor + '" --public-ip ' + $PublicIp) -WorkingDirectory $serverRoot
$trigger = New-ScheduledTaskTrigger -AtStartup
$principal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew -StartWhenAvailable
Register-ScheduledTask -TaskName 'AnotherMe-Hosted-ECS' -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Description 'AnotherMe isolated visitor UI and HTTPS proxy' -Force | Out-Null
Start-ScheduledTask -TaskName 'AnotherMe-Hosted-ECS'
Write-Host ('Task started. Expected public URL: https://' + $PublicIp)
Write-Host 'Allow inbound TCP 80/443 in the Aliyun security group; limit RDP 3389 to your own IP.'
Write-Host ('Logs: ' + (Join-Path $serverRoot 'data\hosted-logs'))
Write-Host 'Certificate issuance and public reachability still need to be verified.'
