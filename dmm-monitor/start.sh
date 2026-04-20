#!/bin/bash
echo "============================================"
echo "  DMM Monitor - Keithley 2400 起動"
echo "  (WebSocket + Firebase 同期)"
echo "============================================"
echo ""
echo "  Ctrl+C で停止できます"
echo "  先に ./sync-server/start_server.sh で"
echo "  WebSocketサーバーを起動してください"
echo ""

cd "$(dirname "$0")"
python3 dmm_sender.py --live
