@echo off
rem Daily scan for Windows Task Scheduler: no pause, no browser, appends to output\daily.log
chcp 65001 > nul
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
if not exist output mkdir output
echo ===== %date% %time% ===== >> output\daily.log
python -m chart_screener scan %* >> output\daily.log 2>&1
set RC=%errorlevel%
echo [exit %RC%] >> output\daily.log
exit /b %RC%
