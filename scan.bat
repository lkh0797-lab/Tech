@echo off
chcp 65001 > nul
cd /d "%~dp0"
rem Python: prefer the 64-bit venv (pandas 2.x needs 64-bit), else python on PATH
set "PY=python"
if exist "%USERPROFILE%\.venvs\chart_screener\Scripts\python.exe" set "PY=%USERPROFILE%\.venvs\chart_screener\Scripts\python.exe"
"%PY%" -m chart_screener scan --open %*
pause
