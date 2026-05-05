@echo off
echo ============================================
echo   DMM Monitor - 一括起動
echo   (Sync Server + Keithley Sender)
echo ============================================
echo.

cd /d "%~dp0"

REM ===== Node.js チェック =====
where node >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo [エラー] Node.js がインストールされていません
    echo   https://nodejs.org/ からLTS版をインストールしてください
    pause
    exit /b 1
)

REM ===== Python チェック =====
where python >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo [エラー] Python がインストールされていません
    echo   https://www.python.org/downloads/ からインストールしてください
    pause
    exit /b 1
)

REM ===== sync-server の依存パッケージ =====
if not exist "sync-server\node_modules" (
    echo [準備] sync-server の依存パッケージをインストール中...
    cd sync-server
    npm install
    cd ..
    echo.
)

REM ===== Sync Server をバックグラウンドで起動 =====
echo [1/2] Sync Server を起動中...
start "DMM-SyncServer" cmd /c "cd /d "%~dp0sync-server" && node server.js && pause"
timeout /t 2 >nul
echo   OK (別ウィンドウで起動済み)
echo.

REM ===== DMM Sender を起動 =====
echo [2/2] DMM Sender を起動中...
echo   Ctrl+C で停止できます
echo.
python dmm_sender.py --live
echo.

REM ===== 終了時に Sync Server も停止 =====
echo DMM Sender が停止しました。Sync Server も停止します...
taskkill /fi "WINDOWTITLE eq DMM-SyncServer" >nul 2>nul
echo 全て停止しました。
pause
