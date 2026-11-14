@echo off
setlocal
cd /d "%~dp0"

echo.
echo  CLIPP3R - one-time setup
echo  This installs CLIPP3R and its Python dependencies on this computer.
echo.

where py.exe >nul 2>nul
if errorlevel 1 (
  echo Python Launcher was not found. Install Python 3.10 or newer from https://www.python.org/downloads/windows/
  echo During setup, enable "Add python.exe to PATH" and install the Python Launcher.
  goto :failed
)

where ffmpeg.exe >nul 2>nul
if errorlevel 1 (
  echo FFmpeg was not found. Install it first, for example:
  echo   winget install --id Gyan.FFmpeg.Shared --exact
  echo Then reopen this setup script.
  goto :failed
)

if not exist ".venv\Scripts\python.exe" (
  echo Creating a private Python environment...
  py -3 -m venv ".venv"
  if errorlevel 1 goto :failed
)

echo Installing CLIPP3R and its dependencies. This may take a while.
".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto :failed
".venv\Scripts\python.exe" -m pip install -e "%~dp0"
if errorlevel 1 goto :failed

echo Creating a desktop shortcut...
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0Install-CLIPP3R-Shortcut.ps1"
if errorlevel 1 goto :failed

echo.
echo Setup complete. Double-click "CLIPP3R - Local" on your desktop to start.
echo The first video may download speech-recognition models.
goto :done

:failed
echo.
echo Setup did not complete. Read the message above, fix the issue, then run setup again.
set "RESULT=1"
goto :finish

:done
set "RESULT=0"

:finish
echo.
pause
exit /b %RESULT%
