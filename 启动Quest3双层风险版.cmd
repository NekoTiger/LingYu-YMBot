@echo off
chcp 65001 >nul
pushd "%~dp0"
"simulation\quest3\tools\platform-tools\adb.exe" -d reverse tcp:8768 tcp:8768
if errorlevel 1 echo USB forwarding is not ready. PC preview is available; authorize the Quest for VR use.
echo Two-contact risk experiment: http://localhost:8768
".venv\Scripts\python.exe" -c "import json,urllib.request; h=json.load(urllib.request.build_opener(urllib.request.ProxyHandler({})).open('http://127.0.0.1:8768/health',timeout=2)); assert h.get('ok') and h.get('controller_version')=='20261117-dual-contact-v1'" >nul 2>&1
if not errorlevel 1 (
  echo The current server is already running. Refresh the Quest browser.
  popd
  pause
  exit /b 0
)
echo Keep this window open. Ctrl+C saves the session and stops the server.
".venv\Scripts\python.exe" -X utf8 -m simulation.quest3.server --risk --port 8768
popd
pause
