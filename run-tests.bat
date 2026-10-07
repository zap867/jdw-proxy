@echo off
rem Copyright (c) 2026 abdurrehmandaudi
rem Required Notice: Copyright (c) 2026 abdurrehmandaudi -- justdowork-proxy
rem Licensed under the PolyForm Noncommercial License 1.0.0 -- commercial
rem use is not permitted without a separate written commercial license.
rem See LICENSE or https://polyformproject.org/licenses/noncommercial/1.0.0
rem Run ccproxy's offline tests. No real API key is needed -- the suite starts
rem its own mock upstream.
setlocal
cd /d "%~dp0"

where uv >nul 2>&1
if not errorlevel 1 (
  uv run test_offline.py %*
  pause
  exit /b 0
)

if not exist ".venv\Scripts\python.exe" (
  echo .venv not found. Run start.bat once first -- it creates it.
  pause
  exit /b 1
)

".venv\Scripts\python.exe" test_offline.py %*
pause
