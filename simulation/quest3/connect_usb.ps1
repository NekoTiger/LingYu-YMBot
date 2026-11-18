param([string]$Serial = '')
$ErrorActionPreference = 'Stop'
$taskAdb = Join-Path $PSScriptRoot 'tools\platform-tools\adb.exe'
if (-not (Test-Path -LiteralPath $taskAdb)) {
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'install_adb.ps1')
    if ($LASTEXITCODE -ne 0) { throw 'Platform Tools installation failed.' }
}
$taskDeviceLines = @(& $taskAdb devices)
if ($LASTEXITCODE -ne 0) { throw 'adb devices failed.' }
$taskDeviceLines | ForEach-Object { Write-Host $_ }
if ($Serial -eq '') {
    $taskDevices = @($taskDeviceLines | Where-Object { $_ -match '^\S+\s+device$' } | ForEach-Object { ($_ -split '\s+')[0] })
    if ($taskDevices.Count -eq 0) { throw 'No authorized device. Enable Quest developer mode, connect a data USB cable, then accept USB debugging INSIDE the headset.' }
    if ($taskDevices.Count -gt 1) { throw 'Multiple devices found. Run connect_usb.ps1 -Serial YOUR_QUEST_SERIAL.' }
    $Serial = $taskDevices[0]
}
& $taskAdb -s $Serial reverse tcp:8765 tcp:8765
if ($LASTEXITCODE -ne 0) { throw 'USB port forwarding failed.' }
Write-Host ''
Write-Host 'USB forwarding ready: Quest localhost:8765 -> PC localhost:8765'
Write-Host 'Keep the simulation launcher running on the PC.'
Write-Host 'In Quest Browser open http://localhost:8765 and choose Enter VR.'
Write-Host 'First release both grip buttons, then hold both to calibrate.'
Write-Host 'To remove forwarding later:'
Write-Host ('  "{0}" -s {1} reverse --remove tcp:8765' -f $taskAdb, $Serial)
