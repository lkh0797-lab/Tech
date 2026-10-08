@echo off
rem Open the newest scan report (output\scan_*.html) in the default browser, without rescanning
cd /d "%~dp0"
set "R="
for /f "delims=" %%f in ('dir /b /o-d "output\scan_*.html" 2^>nul') do if not defined R set "R=%%f"
if not defined R (
  echo No report yet - run scan.bat first.
  pause
  exit /b 1
)
if "%~1"=="--print" ( echo output\%R% & exit /b 0 )
start "" "output\%R%"
