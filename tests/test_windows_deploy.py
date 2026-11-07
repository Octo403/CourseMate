"""Run the real stop script against process/task doubles, never live services."""
import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest


@pytest.mark.skipif(os.name != 'nt', reason='Windows deployment script')
def test_stop_server_finds_base_python_children_and_preserves_other_deployments(tmp_path):
    powershell = shutil.which('powershell.exe')
    if not powershell:
        pytest.skip('Windows PowerShell not installed')
    project = Path(__file__).resolve().parents[1]
    deploy = project/'scripts/deploy/windows'
    stop_script = deploy/'Stop-Server.ps1'
    quote = lambda value: "'"+str(value).replace("'", "''")+"'"
    fixture = rf"""
$ErrorActionPreference = 'Stop'
$fixtureRoot = {quote(project)}
$fixtureDeploy = {quote(deploy)}
$script:stopped = @()
$script:taskActions = @()
function Get-CimInstance {{
    [CmdletBinding()]param([string]$ClassName)
    @(
        [pscustomobject]@{{ProcessId=1;Name='python.exe';CommandLine='python -u "'+$fixtureRoot+'\scripts\run_hosted_server.py" --public-ip 192.0.2.1'}},
        [pscustomobject]@{{ProcessId=2;Name='python.exe';ExecutablePath='C:\base-python\python.exe';CommandLine='python -m aitown.cli hosted-ui --directory "'+$fixtureRoot+'\data\hosted"'}},
        [pscustomobject]@{{ProcessId=3;Name='caddy.exe';CommandLine='caddy run --config "'+$fixtureRoot+'\tools\caddy\Caddyfile"'}},
        [pscustomobject]@{{ProcessId=4;Name='python.exe';CommandLine='python -m aitown.cli hosted-ui --directory C:\OtherApp\data\hosted'}},
        [pscustomobject]@{{ProcessId=5;Name='python.exe';CommandLine='python -m aitown.cli hosted-ui --directory "'+$fixtureRoot+'\data\hosted-other"'}},
        [pscustomobject]@{{ProcessId=6;Name='python.exe';CommandLine='python unrelated.py'}},
        [pscustomobject]@{{ProcessId=7;Name='caddy.exe';CommandLine='caddy run --config C:\OtherApp\Caddyfile'}}
    )
}}
function Get-ScheduledTask {{
    [CmdletBinding()]param([string]$TaskName)
    [pscustomobject]@{{TaskName=$TaskName}}
}}
function Disable-ScheduledTask {{
    [CmdletBinding()]param([string]$TaskName)
    $script:taskActions += 'disable:'+$TaskName
}}
function Stop-ScheduledTask {{
    [CmdletBinding()]param([string]$TaskName)
    $script:taskActions += 'stop:'+$TaskName
}}
function Stop-Process {{
    [CmdletBinding()]param([int]$Id)
    $script:stopped += $Id
}}
$source = Get-Content -LiteralPath {quote(stop_script)} -Raw
$source = $source -replace '(?m)^#Requires[^\r\n]*', ''
$source = '$PSScriptRoot = '+"'"+$fixtureDeploy.Replace("'", "''")+"'"+"`r`n"+$source
& ([scriptblock]::Create($source))
@{{stopped=@($script:stopped);tasks=@($script:taskActions)}} | ConvertTo-Json -Compress
"""
    script = tmp_path/'verify-stop.ps1'
    script.write_text(fixture, encoding='utf-8-sig')
    result = subprocess.run([powershell, '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(script)],
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    summary = json.loads(result.stdout.strip().splitlines()[-1])
    assert summary['stopped'] == [1, 2, 3]
    assert summary['tasks'] == ['disable:AnotherMe-Hosted-ECS', 'stop:AnotherMe-Hosted-ECS']
