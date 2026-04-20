#!/bin/bash
echo "============================================="
echo "  DMM Monitor - WebSocket同期セットアップ"
echo "============================================="
echo ""

# ===== Node.js チェック =====
echo "[1/4] Node.js チェック..."
if ! command -v node &> /dev/null; then
    echo "  [エラー] Node.js がインストールされていません"
    echo "  https://nodejs.org/ からLTS版をインストールしてください"
    exit 1
fi
echo "  Node.js $(node -v)"

# ===== npm install (sync-server) =====
echo ""
echo "[2/4] WebSocketサーバーの依存パッケージをインストール..."
cd "$(dirname "$0")/sync-server"
npm install
cd ..
echo "  完了"

# ===== Python チェック =====
echo ""
echo "[3/4] Python チェック..."
if ! command -v python3 &> /dev/null; then
    echo "  [警告] Python3 が見つかりません (Senderを使う場合は必要)"
else
    echo "  $(python3 -V)"
    echo "  websocket-client をインストール中..."
    pip3 install websocket-client 2>/dev/null || python3 -m pip install websocket-client
fi

# ===== 完了 =====
echo ""
echo "[4/4] セットアップ完了！"
echo ""
echo "============================================="
echo "  使い方:"
echo ""
echo "  1. ./start_server.sh でサーバー起動"
echo "  2. ./start.sh で Python Sender 起動"
echo "  3. ブラウザで index.html を開く"
echo ""
echo "  同じLAN内の他のPCのブラウザからも"
echo "  同じURLにアクセスすればリアルタイム同期！"
echo "============================================="
