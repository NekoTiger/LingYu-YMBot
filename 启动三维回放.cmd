@echo off
chcp 65001 >nul
cd /d "%~dp0"
"%~dp0.venv\Scripts\python.exe" -X utf8 simulation\v2\viewer.py "simulation\research\outputs\demo_dynamic"
if errorlevel 1 pause
