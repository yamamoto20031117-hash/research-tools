#!/bin/bash
# DMM Monitor 2 — macOS 起動スクリプト
# Keithley 2400 SourceMeter をこのMacに接続して使用
#
# 使い方:
#   chmod +x start.sh
#   ./start.sh              # テストモード（ダミーデータ）
#   ./start.sh --live       # 実機モード（Keithley 2400 に接続）
#   ./start.sh --list       # 接続デバイス一覧

cd "$(dirname "$0")"

# Python依存パッケージチェック
echo "=== DMM Monitor 2 — Keithley 2400 Sender ==="
echo ""

# 必要パッケージの確認
MISSING=()
python3 -c "import pyvisa" 2>/dev/null || MISSING+=("pyvisa")
python3 -c "import serial" 2>/dev/null || MISSING+=("pyserial")
python3 -c "import websocket" 2>/dev/null || MISSING+=("websocket-client")

if [ ${#MISSING[@]} -gt 0 ]; then
    echo "必要なパッケージが不足しています: ${MISSING[*]}"
    echo "インストールしますか? (y/n)"
    read -r ans
    if [ "$ans" = "y" ] || [ "$ans" = "Y" ]; then
        pip3 install pyvisa pyvisa-py pyserial websocket-client
    else
        echo "パッケージをインストールしてから再実行してください:"
        echo "  pip3 install pyvisa pyvisa-py pyserial websocket-client"
        exit 1
    fi
fi

echo ""
echo "引数: $*"
echo "---"
python3 dmm_sender.py "$@"
