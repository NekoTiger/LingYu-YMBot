@echo off
chcp 65001 >nul
pushd "%~dp0"
"simulation\quest3\tools\platform-tools\adb.exe" -d reverse tcp:8766 tcp:8766
if errorlevel 1 (
  echo USB forwarding is not ready. Connect and authorize the Quest, then run this launcher again.
  popd
  pause
  exit /b 1
)
echo Quest experiment: http://localhost:8766
".venv\Scripts\python.exe" -c "import json,urllib.request; h=json.load(urllib.request.build_opener(urllib.request.ProxyHandler({})).open('http://127.0.0.1:8766/health',timeout=2)); assert h.get('ok') and 'study_sessions' in h.get('session','')" >nul 2>&1
if not errorlevel 1 (
  echo The experiment server is already running. USB forwarding has been restored.
  echo Refresh http://localhost:8766 in the Quest browser to continue.
  popd
  pause
  exit /b 0
)
echo Keep this window open. Ctrl+C saves the current session and stops the server.
".venv\Scripts\python.exe" -X utf8 -m simulation.quest3.server --study --port 8766
popd
pause
