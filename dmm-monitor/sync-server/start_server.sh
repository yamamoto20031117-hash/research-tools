#!/bin/bash
echo "============================================"
echo "  DMM Sync Server - 起動スクリプト"
echo "============================================"
echo ""

# Node.js チェック
if ! command -v node &> /dev/null; then
    echo "[エラー] Node.js がインストールされていません"
    echo "  https://nodejs.org/ からインストールしてください"
    exit 1
fi

# sync-serverディレクトリに移動
cd "$(dirname "$0")"

# 依存パッケージチェック
if [ ! -d "node_modules" ]; then
    echo "npm install を実行中..."
    npm install
    echo ""
fi

echo "サーバーを起動します..."
echo "  停止: Ctrl+C"
echo ""
node server.js --verbose
