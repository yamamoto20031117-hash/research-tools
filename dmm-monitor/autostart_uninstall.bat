@echo off
echo ============================================
echo   DMM Monitor - 自動起動を解除
echo ============================================
echo.

set STARTUP_DIR=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup

if exist "%STARTUP_DIR%\DMM_Monitor.lnk" (
    del "%STARTUP_DIR%\DMM_Monitor.lnk"
    echo [完了] 自動起動を解除しました。
) else (
    echo 自動起動は設定されていません。
)

REM VBSファイルも削除
if exist "%~dp0dmm_autostart.vbs" del "%~dp0dmm_autostart.vbs"

echo.
pause
