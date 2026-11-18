$ErrorActionPreference = 'Stop'
$taskTools = Join-Path $PSScriptRoot 'tools'
$taskAdb = Join-Path $taskTools 'platform-tools\adb.exe'
if (Test-Path -LiteralPath $taskAdb) {
    & $taskAdb version
    exit $LASTEXITCODE
}
New-Item -ItemType Directory -Force -Path $taskTools | Out-Null
$taskUrl = 'https://dl.google.com/android/repository/platform-tools-latest-windows.zip'
$taskZip = Join-Path $taskTools 'platform-tools-windows.zip'
Write-Host 'Downloading Android Platform Tools from dl.google.com ...'
Invoke-WebRequest -Uri $taskUrl -OutFile $taskZip -TimeoutSec 60
$taskHash = (Get-FileHash -LiteralPath $taskZip -Algorithm SHA256).Hash
Expand-Archive -LiteralPath $taskZip -DestinationPath $taskTools -Force
@{ url = $taskUrl; sha256 = $taskHash; installed_utc = [DateTime]::UtcNow.ToString('o') } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $taskTools 'download.json') -Encoding UTF8
if (-not (Test-Path -LiteralPath $taskAdb)) { throw 'adb.exe was not found after extraction.' }
& $taskAdb version
if ($LASTEXITCODE -ne 0) { throw 'adb version failed.' }
Write-Host 'Installed inside this project. System PATH was not changed.'
