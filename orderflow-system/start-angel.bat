@echo off
rem Starts the API and the UI in two windows, then opens the browser. Close both windows to stop.
cd /d "%~dp0backend"
set OFX_PROVIDER=angel
rem Angel keys are read from backend\.env
start "OFX API (keep open)" cmd /k "python -m uvicorn ofx.main:app --port 8000"
cd /d "%~dp0frontend"
if not exist node_modules call npm ci
start "OFX UI (keep open)" cmd /k "npm run dev"
timeout /t 8 >nul
start http://localhost:5173
