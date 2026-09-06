@echo off
setlocal
title TTS Studio

echo ================================================
echo   TTS Studio - one-click launcher
echo ================================================
echo.
echo NOTE: messages are in English to avoid codepage garbling.
echo.

cd /d "%~dp0"

echo [1/4] Freeing port 8000 if an old instance is still running...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8000" ^| findstr "LISTENING"') do (
    echo      Killing stale process PID %%a
    taskkill /F /PID %%a >nul 2>&1
)

echo [2/4] Installing backend dependencies (python -m pip)...
cd backend
python -m pip install -r requirements.txt -q
if errorlevel 1 (
    echo ERROR: backend dependency install failed. Check your Python environment.
    pause
    exit /b 1
)

echo [3/4] Checking frontend dependencies and building...
cd ..\frontend
if not exist node_modules (
    echo      First run: installing npm packages, please wait...
    call npm install --no-audit --no-fund
    if errorlevel 1 (
        echo ERROR: npm install failed. Check your Node.js environment.
        pause
        exit /b 1
    )
)
call npm run build
if errorlevel 1 (
    echo ERROR: frontend build failed.
    pause
    exit /b 1
)

echo [4/4] Starting server on http://127.0.0.1:8000
echo      Browser will open automatically in a few seconds.
echo      Keep this window open while using the app. Ctrl+C to stop.
cd ..
start "" /min cmd /c "ping -n 4 127.0.0.1 >nul & start http://127.0.0.1:8000"
cd backend
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000

echo.
echo Server exited. Press any key to close this window.
pause >nul
