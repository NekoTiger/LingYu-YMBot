@echo off
chcp 65001 >nul
pushd "%~dp0"
"simulation\quest3\tools\platform-tools\adb.exe" -d reverse tcp:8767 tcp:8767
if errorlevel 1 echo USB forwarding is not ready. PC preview is still available; authorize the Quest before VR use.
echo Workspace-follow pilot: http://localhost:8767
".venv\Scripts\python.exe" -c "import json,urllib.request; h=json.load(urllib.request.build_opener(urllib.request.ProxyHandler({})).open('http://127.0.0.1:8767/health',timeout=2)); assert h.get('ok') and h.get('controller_version')=='20261117-follow3'" >nul 2>&1
if not errorlevel 1 (
  echo The current server is already running. Refresh the Quest browser to continue.
  popd
  pause
  exit /b 0
)
echo Keep this window open. Ctrl+C saves the session and stops the server.
".venv\Scripts\python.exe" -X utf8 -m simulation.quest3.server --follow --port 8767
popd
pause
