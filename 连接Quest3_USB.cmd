@echo off
chcp 65001 >nul
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0simulation\quest3\connect_usb.ps1"
pause
