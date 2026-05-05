@echo off
echo ============================================
echo   DMM Monitor - 全停止
echo ============================================
echo.
echo Python Sender を停止中...
taskkill /f /im python.exe >nul 2>nul
echo Sync Server を停止中...
taskkill /fi "WINDOWTITLE eq DMM-SyncServer" >nul 2>nul
taskkill /f /fi "IMAGENAME eq node.exe" /fi "WINDOWTITLE eq DMM-SyncServer" >nul 2>nul
echo.
echo   全て停止しました
pause
