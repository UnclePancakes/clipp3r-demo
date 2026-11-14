@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo CLIPP3R has not been set up on this computer yet.
  echo Double-click Setup-CLIPP3R.bat first.
  echo.
  pause
  exit /b 1
)

powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0Start-CLIPP3R.ps1"
set "RESULT=%ERRORLEVEL%"
if not "%RESULT%"=="0" (
  echo.
  echo CLIPP3R stopped with an error. Review the message above.
)
echo.
pause
exit /b %RESULT%
