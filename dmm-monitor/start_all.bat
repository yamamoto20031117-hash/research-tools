@echo off
chcp 65001 >nul 2>nul
echo ============================================
echo   DMM Monitor - 一括起動
echo   (Sync Server + Keithley Sender)
echo ============================================
echo.

cd /d "%~dp0"

REM ===== Node.js チェック =====
where node >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo [Error] Node.js not found.
    echo   https://nodejs.org/
    pause
    exit /b 1
)

REM ===== Python チェック =====
where python >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo [Error] Python not found.
    echo   https://www.python.org/downloads/
    pause
    exit /b 1
)

REM ===== sync-server の依存パッケージ =====
if not exist "sync-server\node_modules" (
    echo [Setup] Installing sync-server dependencies...
    cd sync-server
    npm install
    cd ..
    echo.
)

REM ===== Sync Server をバックグラウンドで起動 =====
echo [1/2] Starting Sync Server...
start "DMM-SyncServer" cmd /k "cd /d "%~dp0sync-server" && node server.js"
timeout /t 2 >nul
echo   OK
echo.

REM ===== DMM Sender を起動 =====
echo [2/2] Starting DMM Sender...
echo   Press Ctrl+C to stop
echo.
python dmm_sender.py --live
echo.

REM ===== 終了時に Sync Server も停止 =====
echo Stopping Sync Server...
taskkill /fi "WINDOWTITLE eq DMM-SyncServer" >nul 2>nul
echo All stopped.
pause
