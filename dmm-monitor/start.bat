@echo off
echo ============================================
echo   DMM Monitor - Keithley 2400 起動
echo ============================================
echo.
echo   Ctrl+C で停止できます
echo.
python dmm_sender.py --live
pause
