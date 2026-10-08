@echo off
rem Daily scan for Windows Task Scheduler: no pause, no browser, appends to output\daily.log
chcp 65001 > nul
cd /d "%~dp0"
rem Python: prefer the 64-bit venv (pandas 2.x needs 64-bit), else python on PATH
set "PY=python"
if exist "%USERPROFILE%\.venvs\chart_screener\Scripts\python.exe" set "PY=%USERPROFILE%\.venvs\chart_screener\Scripts\python.exe"
set PYTHONIOENCODING=utf-8
if not exist output mkdir output
echo ===== %date% %time% ===== >> output\daily.log
"%PY%" -m chart_screener scan %* >> output\daily.log 2>&1
set RC=%errorlevel%
echo [exit %RC%] >> output\daily.log
exit /b %RC%
