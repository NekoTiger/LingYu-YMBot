@echo off
chcp 65001 >nul
"%~dp0simulation\quest3\tools\platform-tools\adb.exe" shell am start -a android.intent.action.VIEW -d "http://localhost:8768/" com.oculus.browser
