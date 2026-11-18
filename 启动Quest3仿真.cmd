@echo off
chcp 65001 >nul
pushd "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Project Python environment is missing. See simulation\quest3\README.md
  pause
  exit /b 1
)
echo LingYu Quest 3 - live MuJoCo simulation
echo PC viewer: http://localhost:8765
echo Keep this window open. Press Ctrl+C to stop and finish recording.
".venv\Scripts\python.exe" -X utf8 -m simulation.quest3.server
popd
pause
