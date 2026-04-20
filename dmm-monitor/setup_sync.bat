@echo off
echo =============================================
echo   DMM Monitor - WebSocket同期セットアップ
echo =============================================
echo.

REM ===== Node.js チェック =====
echo [1/4] Node.js チェック...
where node >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo   [エラー] Node.js がインストールされていません
    echo   https://nodejs.org/ からLTS版をインストールしてください
    pause
    exit /b 1
)
for /f "tokens=*" %%i in ('node -v') do echo   Node.js %%i

REM ===== npm install (sync-server) =====
echo.
echo [2/4] WebSocketサーバーの依存パッケージをインストール...
cd sync-server
call npm install
cd ..
echo   完了

REM ===== Python チェック =====
echo.
echo [3/4] Python チェック...
where python >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo   [警告] Python が見つかりません (Senderを使う場合は必要)
) else (
    for /f "tokens=*" %%i in ('python -V') do echo   %%i
    echo   websocket-client をインストール中...
    pip install websocket-client --break-system-packages 2>nul || pip install websocket-client
)

REM ===== 完了 =====
echo.
echo [4/4] セットアップ完了！
echo.
echo =============================================
echo   使い方:
echo.
echo   1. sync-server\start_server.bat でサーバー起動
echo   2. start.bat で Python Sender 起動
echo   3. ブラウザで index.html を開く
echo.
echo   同じLAN内の他のPCのブラウザからも
echo   同じURLにアクセスすればリアルタイム同期！
echo =============================================
pause
