@echo off
echo ============================================
echo   DMM Monitor - Keithley 2400 起動
echo   (WebSocket + Firebase 同期)
echo ============================================
echo.
echo   Ctrl+C で停止できます
echo   先に sync-server\start_server.bat で
echo   WebSocketサーバーを起動してください
echo.
python dmm_sender.py --live
pause
