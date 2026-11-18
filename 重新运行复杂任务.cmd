@echo off
chcp 65001 >nul
cd /d "%~dp0"
"%~dp0.venv\Scripts\python.exe" -X utf8 simulation\research\research_runner_v2.py --seed 401 --dynamic --noise .006 --latency .08 --dropout .1 --target-height .75 --out "simulation\research\outputs\acceptance_run"
if errorlevel 1 pause
