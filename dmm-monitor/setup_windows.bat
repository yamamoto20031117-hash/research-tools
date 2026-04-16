@echo off
echo ============================================
echo   DMM Monitor - Windows セットアップ
echo ============================================
echo.

REM Python確認
python --version >nul 2>&1
if errorlevel 1 (
    echo [エラー] Python がインストールされていません。
    echo https://www.python.org/downloads/ からインストールしてください。
    echo インストール時に「Add Python to PATH」にチェックを入れてください。
    pause
    exit /b 1
)

echo [1/3] Python パッケージをインストール中...
pip install pyvisa pyvisa-py pyserial
echo.

echo [2/3] VISA リソースを確認中...
python dmm_sender.py --list
echo.

echo [3/3] セットアップ完了！
echo.
echo 次のステップ:
echo   1. 上記の VISA リソース一覧から Keithley の COM ポートを確認
echo   2. dmm_sender.py の DMM_ADDRESS を書き換え（例: "ASRL3::INSTR"）
echo   3. 起動コマンド: python dmm_sender.py --live
echo.
pause
