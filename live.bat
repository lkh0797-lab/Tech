@echo off
rem Live watch (read-only, never places orders). e.g. live.bat --source naver  /  live.bat --check
chcp 65001 > nul
cd /d "%~dp0"
rem Python: prefer the 64-bit venv (pandas 2.x needs 64-bit), else python on PATH
set "PY=python"
if exist "%USERPROFILE%\.venvs\chart_screener\Scripts\python.exe" set "PY=%USERPROFILE%\.venvs\chart_screener\Scripts\python.exe"
set PYTHONIOENCODING=utf-8
"%PY%" -m chart_screener live %*
pause
