@echo off
rem Live watch (read-only, never places orders). e.g. live.bat --source naver  /  live.bat --check
chcp 65001 > nul
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
python -m chart_screener live %*
pause
