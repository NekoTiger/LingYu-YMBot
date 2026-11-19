$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$adb = Join-Path $root 'simulation\quest3\tools\platform-tools\adb.exe'
$log = Join-Path $root 'vr_watchdog.log'
$lastReload = [datetime]::MinValue
$disconnectedSince = $null

function Log($msg) {
    $line = '{0} {1}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $msg
    Add-Content -LiteralPath $log -Value $line -Encoding UTF8
    Write-Host $line
}

Log 'watchdog started'
while ($true) {
    try {
        $devices = & $adb devices 2>$null
        $online = $devices -match '^\S+\s+device$'
        if (-not $online) {
            Log 'no authorized device'
        } else {
            $rev = (& $adb reverse --list 2>$null) -join "`n"
            if ($rev -notmatch 'tcp:8768') {
                & $adb reverse tcp:8768 tcp:8768 2>$null | Out-Null
                Log 'reverse re-added (tcp:8768)'
            }
        }
        try {
            $h = (Invoke-WebRequest -Uri 'http://127.0.0.1:8768/health' -UseBasicParsing -TimeoutSec 3).Content | ConvertFrom-Json
            $trialState = $h.experiment.status
            if ($h.clients -lt 2) {
                if ($null -eq $disconnectedSince) { $disconnectedSince = Get-Date }
                $downSec = ((Get-Date) - $disconnectedSince).TotalSeconds
                if ($trialState -notin @('running', 'ready') -and $downSec -ge 45 -and ((Get-Date) - $lastReload).TotalSeconds -gt 60) {
                    & (Join-Path $root '_open_quest.cmd') 2>$null | Out-Null
                    $lastReload = Get-Date
                    Log ('quest page reopened after ' + [int]$downSec + 's disconnected (clients=' + $h.clients + ', trial=' + $trialState + ')')
                }
            } else {
                $disconnectedSince = $null
            }
        } catch {
            # server busy or restarting: keep reverse alive only, do not touch the page
        }
    } catch {
        Log ('loop error: ' + $_.Exception.Message)
    }
    Start-Sleep -Seconds 3
}
