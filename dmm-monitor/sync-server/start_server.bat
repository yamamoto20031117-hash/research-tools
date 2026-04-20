@echo off
echo ============================================
echo   DMM Sync Server - 起動スクリプト
echo ============================================
echo.

REM Node.js チェック
where node >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo [エラー] Node.js がインストールされていません
    echo   https://nodejs.org/ からインストールしてください
    pause
    exit /b 1
)

REM 依存パッケージチェック
if not exist node_modules (
    echo npm install を実行中...
    npm install
    echo.
)

echo サーバーを起動します...
echo   停止: Ctrl+C
echo.
node server.js --verbose

pause
