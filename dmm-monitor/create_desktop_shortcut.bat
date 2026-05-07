@echo off
chcp 65001 >nul 2>nul
echo Creating desktop shortcut for DMM Monitor...

set SCRIPT_DIR=%~dp0
set DESKTOP=%USERPROFILE%\Desktop

echo Set oWS = WScript.CreateObject("WScript.Shell") > "%TEMP%\dmm_shortcut.vbs"
echo Set oLink = oWS.CreateShortcut("%DESKTOP%\DMM Monitor.lnk") >> "%TEMP%\dmm_shortcut.vbs"
echo oLink.TargetPath = "%SCRIPT_DIR%start_all.bat" >> "%TEMP%\dmm_shortcut.vbs"
echo oLink.WorkingDirectory = "%SCRIPT_DIR%" >> "%TEMP%\dmm_shortcut.vbs"
echo oLink.Description = "DMM Monitor - Start All" >> "%TEMP%\dmm_shortcut.vbs"
echo oLink.Save >> "%TEMP%\dmm_shortcut.vbs"

cscript //nologo "%TEMP%\dmm_shortcut.vbs"
del "%TEMP%\dmm_shortcut.vbs"

echo.
echo Done! "DMM Monitor" shortcut created on Desktop.
echo Double-click it to start.
pause
