@echo off
rem タイムカード(打刻・勤怠・給与)を起動する。
setlocal
cd /d "%~dp0"

set "PY=python"
where py >nul 2>nul && set "PY=py -3"

%PY% --version >nul 2>nul
if errorlevel 1 (
  echo Python 3.10+ is required. Install it from https://www.python.org/downloads/
  pause
  exit /b 1
)

if not exist ".venv" (
  echo Setting up for the first time. This takes about a minute...
  %PY% -m venv .venv
)
rem Skip the install when the libraries are already there (fast restarts).
".venv\Scripts\python.exe" -c "import flask" >nul 2>nul
if errorlevel 1 (
  echo Installing required libraries...
  ".venv\Scripts\python.exe" -m pip install --quiet -r requirements.txt
  if errorlevel 1 (
    echo.
    echo Failed to install the libraries. Check your network connection and try again.
    pause
    exit /b 1
  )
)

if "%PORT%"=="" set "PORT=5000"
echo.
echo   Timecard -^> http://127.0.0.1:%PORT%
echo   Press Ctrl+C in this window to stop.
echo.
start "" "http://127.0.0.1:%PORT%"
".venv\Scripts\python.exe" run.py
pause
