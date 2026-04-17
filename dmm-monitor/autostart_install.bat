@echo off
echo ============================================
echo   DMM Monitor - 自動起動セットアップ
echo ============================================
echo.

REM 現在のフォルダパスを取得
set SCRIPT_DIR=%~dp0
set SCRIPT_PATH=%SCRIPT_DIR%dmm_sender.py

REM Python確認
python --version >nul 2>&1
if errorlevel 1 (
    echo [エラー] Python が見つかりません。先にインストールしてください。
    pause
    exit /b 1
)

REM Pythonのフルパスを取得
for /f "delims=" %%i in ('where python') do set PYTHON_PATH=%%i

echo Python: %PYTHON_PATH%
echo Script: %SCRIPT_PATH%
echo.

REM VBSスクリプトを作成（非表示でPythonを起動）
echo Set WshShell = CreateObject("WScript.Shell") > "%SCRIPT_DIR%dmm_autostart.vbs"
echo WshShell.CurrentDirectory = "%SCRIPT_DIR%" >> "%SCRIPT_DIR%dmm_autostart.vbs"
echo WshShell.Run "cmd /c ""%PYTHON_PATH%"" ""%SCRIPT_PATH%"" --live", 1, False >> "%SCRIPT_DIR%dmm_autostart.vbs"

REM スタートアップフォルダにショートカットを作成
set STARTUP_DIR=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup
echo スタートアップフォルダ: %STARTUP_DIR%

REM 既存のショートカットを削除
if exist "%STARTUP_DIR%\DMM_Monitor.lnk" del "%STARTUP_DIR%\DMM_Monitor.lnk"

REM VBSへのショートカットをスタートアップに作成
echo Set oWS = WScript.CreateObject("WScript.Shell") > "%TEMP%\create_shortcut.vbs"
echo Set oLink = oWS.CreateShortcut("%STARTUP_DIR%\DMM_Monitor.lnk") >> "%TEMP%\create_shortcut.vbs"
echo oLink.TargetPath = "wscript.exe" >> "%TEMP%\create_shortcut.vbs"
echo oLink.Arguments = """%SCRIPT_DIR%dmm_autostart.vbs""" >> "%TEMP%\create_shortcut.vbs"
echo oLink.WorkingDirectory = "%SCRIPT_DIR%" >> "%TEMP%\create_shortcut.vbs"
echo oLink.Description = "DMM Monitor Auto Start" >> "%TEMP%\create_shortcut.vbs"
echo oLink.Save >> "%TEMP%\create_shortcut.vbs"
cscript //nologo "%TEMP%\create_shortcut.vbs"
del "%TEMP%\create_shortcut.vbs"

echo.
echo [完了] 自動起動を設定しました！
echo   - PCを起動すると自動でDMM Monitorが立ち上がります
echo   - シャットダウン時は自動で終了します
echo   - 解除するには autostart_uninstall.bat を実行してください
echo.
pause
