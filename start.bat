@echo off
rem Copyright (c) 2026 abdurrehmandaudi
rem Required Notice: Copyright (c) 2026 abdurrehmandaudi -- justdowork-proxy
rem Licensed under the PolyForm Noncommercial License 1.0.0 -- commercial
rem use is not permitted without a separate written commercial license.
rem See LICENSE or https://polyformproject.org/licenses/noncommercial/1.0.0
rem ---------------------------------------------------------------------------
rem  Start ccproxy on Windows with uv (or python fallback).
rem  Double-click this file, or run it from cmd / PowerShell:  start.bat
rem ---------------------------------------------------------------------------
setlocal
cd /d "%~dp0"

where uv >nul 2>&1
if not errorlevel 1 (
  echo [uv] Using uv environment manager...
  echo Starting ccproxy ... the exact URL is printed on the next line.
  echo Press Ctrl+C to stop.
  echo.
  uv run ccproxy.py
  if errorlevel 1 goto fail
  exit /b 0
)

where python >nul 2>&1
if errorlevel 1 (
  echo.
  echo !! Neither uv nor Python 3 was found on your PATH.
  echo.
  echo    Install uv (recommended):  powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
  echo    Or install Python from:     https://www.python.org/downloads/
  echo.
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo Creating .venv -- first run only, this takes a minute ...
  python -m venv .venv
  if errorlevel 1 goto fail
  echo Installing dependencies ...
  ".venv\Scripts\python.exe" -m pip install --upgrade pip
  if errorlevel 1 goto fail
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt
  if errorlevel 1 goto fail
)

echo.
echo Starting ccproxy ... the exact URL is printed on the next line.
echo Press Ctrl+C to stop.
echo.

".venv\Scripts\python.exe" ccproxy.py
if errorlevel 1 goto fail
exit /b 0

:fail
echo.
echo Process exited or failed.
echo.
pause
exit /b 1
