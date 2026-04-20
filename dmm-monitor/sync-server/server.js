#!/usr/bin/env node
/**
 * DMM Sync Server — 超低レイテンシ WebSocket リレー
 *
 * アーキテクチャ:
 *   Python (dmm_sender.py) → WebSocket Server → 全ブラウザクライアント
 *
 * 最速のために:
 *   - ws ライブラリ (Node.js最速のWebSocket実装)
 *   - バイナリメッセージ (Float64Array: 24バイト固定)
 *   - 圧縮無効 (perMessageDeflate: false)
 *   - Nagleアルゴリズム無効 (socket.setNoDelay(true))
 *   - 即時ブロードキャスト (バッファリングなし)
 *   - サーバー内タイムスタンプ (クライアント間の時計差を吸収)
 *
 * 使い方:
 *   cd sync-server
 *   npm install
 *   node server.js                  # デフォルト (port 8765)
 *   node server.js --port 9000      # ポート指定
 *   node server.js --verbose        # 詳細ログ
 *
 * プロトコル:
 *   接続時: JSON { type: "hello", role: "sender"|"viewer", ... }
 *   データ: バイナリ 24バイト [timestamp_ms(f64), voltage(f64), current(f64)]
 *   制御:   JSON { type: "command"|"status"|"sync_request"|"sync_response", ... }
 */

const { WebSocketServer, WebSocket } = require('ws');
const http = require('http');

// ===== 設定 =====
const args = process.argv.slice(2);
const PORT = parseInt(getArg('--port') || '8765');
const VERBOSE = args.includes('--verbose') || args.includes('--dev');
const PING_INTERVAL = 10000;  // 10秒ごとに生存確認
const STALE_TIMEOUT = 30000;  // 30秒応答なしで切断

function getArg(name) {
  const idx = args.indexOf(name);
  return idx >= 0 && idx + 1 < args.length ? args[idx + 1] : null;
}

// ===== HTTP + WebSocket サーバー =====
const httpServer = http.createServer((req, res) => {
  // ヘルスチェック & CORS
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

  if (req.method === 'OPTIONS') {
    res.writeHead(204);
    res.end();
    return;
  }

  if (req.url === '/health' || req.url === '/') {
    const status = {
      ok: true,
      uptime: process.uptime(),
      senders: countByRole('sender'),
      viewers: countByRole('viewer'),
      totalClients: clients.size,
      lastDataTime: lastData ? lastData.time : null,
      latencyStats: getLatencyStats(),
    };
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify(status));
    return;
  }

  res.writeHead(404);
  res.end('Not found');
});

const wss = new WebSocketServer({
  server: httpServer,
  perMessageDeflate: false,    // 圧縮なし = 最速
  maxPayload: 1024 * 64,      // 64KB上限
  backlog: 128,
});

// ===== クライアント管理 =====
const clients = new Map();  // ws -> { role, id, connectedAt, lastPong, latencies }
let clientIdCounter = 0;
let lastData = null;         // 最新データ (新規接続者に即送信)
let lastDataBinary = null;   // バイナリ版
let dataCount = 0;
let broadcastLatencies = []; // 直近のブロードキャスト時間

function countByRole(role) {
  let n = 0;
  for (const info of clients.values()) {
    if (info.role === role) n++;
  }
  return n;
}

function getLatencyStats() {
  if (broadcastLatencies.length === 0) return null;
  const sorted = [...broadcastLatencies].sort((a, b) => a - b);
  return {
    count: sorted.length,
    min: sorted[0].toFixed(3) + 'ms',
    median: sorted[Math.floor(sorted.length / 2)].toFixed(3) + 'ms',
    p99: sorted[Math.floor(sorted.length * 0.99)].toFixed(3) + 'ms',
    max: sorted[sorted.length - 1].toFixed(3) + 'ms',
  };
}

// ===== WebSocket イベント =====
wss.on('connection', (ws, req) => {
  const id = ++clientIdCounter;
  const ip = req.socket.remoteAddress;

  // TCP Nagle無効化 = 即時送信
  if (req.socket.setNoDelay) {
    req.socket.setNoDelay(true);
  }

  const info = {
    role: 'viewer',  // デフォルト; hello メッセージで変更
    id,
    ip,
    connectedAt: Date.now(),
    lastPong: Date.now(),
  };
  clients.set(ws, info);

  log(`[+] Client #${id} connected from ${ip} (total: ${clients.size})`);

  // Pong ハンドラ
  ws.on('pong', () => {
    info.lastPong = Date.now();
  });

  ws.on('message', (data, isBinary) => {
    if (isBinary) {
      // バイナリデータ = 測定値 (senderからのみ)
      if (info.role !== 'sender') return;
      handleBinaryData(ws, data, info);
    } else {
      // JSONメッセージ
      try {
        const msg = JSON.parse(data.toString());
        handleJsonMessage(ws, msg, info);
      } catch (e) {
        if (VERBOSE) log(`[!] Invalid JSON from #${id}`);
      }
    }
  });

  ws.on('close', (code, reason) => {
    clients.delete(ws);
    log(`[-] Client #${id} (${info.role}) disconnected [${code}] (total: ${clients.size})`);

    // sender が切断したら viewer に通知
    if (info.role === 'sender') {
      broadcast(JSON.stringify({
        type: 'sender_disconnected',
        time: Date.now(),
      }), null, false);
    }
  });

  ws.on('error', (err) => {
    if (VERBOSE) log(`[!] Error from #${id}: ${err.message}`);
  });
});

// ===== メッセージハンドラ =====
function handleJsonMessage(ws, msg, info) {
  switch (msg.type) {
    case 'hello': {
      info.role = msg.role === 'sender' ? 'sender' : 'viewer';
      log(`[*] Client #${info.id} role = ${info.role}`);

      // 応答: 接続確認 + サーバー情報
      ws.send(JSON.stringify({
        type: 'welcome',
        id: info.id,
        role: info.role,
        serverTime: Date.now(),
        senders: countByRole('sender'),
        viewers: countByRole('viewer'),
      }));

      // viewer に最新データを即座に送信
      if (info.role === 'viewer' && lastDataBinary) {
        ws.send(lastDataBinary);
      }
      break;
    }

    case 'command': {
      // viewer → sender へコマンド転送
      if (info.role !== 'viewer') return;
      const cmdStr = JSON.stringify(msg);
      for (const [client, clientInfo] of clients) {
        if (clientInfo.role === 'sender' && client.readyState === WebSocket.OPEN) {
          client.send(cmdStr);
        }
      }
      if (VERBOSE) log(`[CMD] ${msg.action} from viewer #${info.id}`);
      break;
    }

    case 'status': {
      // sender → all viewers
      if (info.role !== 'sender') return;
      broadcast(JSON.stringify(msg), ws, false);
      break;
    }

    case 'data_json': {
      // JSON形式のデータ (バイナリが使えない環境用フォールバック)
      if (info.role !== 'sender') return;
      const t = msg.time || Date.now();
      const v = msg.voltage || 0;
      const i = msg.current || 0;

      // バイナリに変換してブロードキャスト
      const buf = new Float64Array([t, v, i]);
      const binary = Buffer.from(buf.buffer);
      lastData = { time: t, voltage: v, current: i };
      lastDataBinary = binary;
      dataCount++;

      broadcast(binary, ws, true);
      if (VERBOSE && dataCount % 10 === 0) {
        log(`[D] #${dataCount} V=${v.toFixed(6)} I=${i.toFixed(9)}`);
      }
      break;
    }

    case 'sync_request': {
      // 新規 viewer が全履歴を要求 → sender に転送
      for (const [client, clientInfo] of clients) {
        if (clientInfo.role === 'sender' && client.readyState === WebSocket.OPEN) {
          client.send(JSON.stringify({ type: 'sync_request', viewerId: info.id }));
        }
      }
      break;
    }

    case 'sync_response': {
      // sender → 特定 viewer へ履歴データ
      const targetId = msg.viewerId;
      for (const [client, clientInfo] of clients) {
        if (clientInfo.id === targetId && client.readyState === WebSocket.OPEN) {
          client.send(JSON.stringify(msg));
        }
      }
      break;
    }

    case 'ping_measure': {
      // レイテンシ測定用: 即座に返す
      ws.send(JSON.stringify({
        type: 'pong_measure',
        clientTime: msg.clientTime,
        serverTime: Date.now(),
      }));
      break;
    }

    default:
      if (VERBOSE) log(`[?] Unknown message type: ${msg.type} from #${info.id}`);
  }
}

function handleBinaryData(ws, data, info) {
  // 24バイト: [timestamp(f64), voltage(f64), current(f64)]
  if (data.length < 24) return;

  const buf = Buffer.from(data);
  lastDataBinary = buf;

  // パースしてキャッシュ
  const view = new Float64Array(buf.buffer, buf.byteOffset, 3);
  lastData = { time: view[0], voltage: view[1], current: view[2] };
  dataCount++;

  // 全 viewer にバイナリで即時ブロードキャスト
  const t0 = performance.now();
  broadcast(buf, ws, true);
  const elapsed = performance.now() - t0;

  broadcastLatencies.push(elapsed);
  if (broadcastLatencies.length > 1000) broadcastLatencies = broadcastLatencies.slice(-500);

  if (VERBOSE && dataCount % 10 === 0) {
    log(`[D] #${dataCount} V=${lastData.voltage.toFixed(6)} I=${lastData.current.toFixed(9)} broadcast=${elapsed.toFixed(3)}ms clients=${countByRole('viewer')}`);
  }
}

// ===== ブロードキャスト =====
function broadcast(data, exclude, isBinary) {
  for (const [client, info] of clients) {
    if (client === exclude) continue;
    if (client.readyState !== WebSocket.OPEN) continue;
    // sender にはデータを返さない (echoを防ぐ)
    if (isBinary && info.role === 'sender') continue;
    try {
      client.send(data, { binary: isBinary });
    } catch (e) {
      // 送信失敗は無視（closeイベントで処理）
    }
  }
}

// ===== Ping / Heartbeat =====
const pingTimer = setInterval(() => {
  const now = Date.now();
  for (const [ws, info] of clients) {
    if (now - info.lastPong > STALE_TIMEOUT) {
      log(`[!] Client #${info.id} timed out, disconnecting`);
      ws.terminate();
      clients.delete(ws);
      continue;
    }
    if (ws.readyState === WebSocket.OPEN) {
      ws.ping();
    }
  }
}, PING_INTERVAL);

// ===== 起動 =====
httpServer.listen(PORT, '0.0.0.0', () => {
  console.log('');
  console.log('╔══════════════════════════════════════════════════════╗');
  console.log('║     DMM Sync Server — Ultra-Low-Latency Relay       ║');
  console.log('╠══════════════════════════════════════════════════════╣');
  console.log(`║  WebSocket:  ws://0.0.0.0:${PORT}                    ║`);
  console.log(`║  Health:     http://0.0.0.0:${PORT}/health            ║`);
  console.log(`║  Verbose:    ${VERBOSE ? 'ON' : 'OFF'}                                    ║`);
  console.log('╠══════════════════════════════════════════════════════╣');
  console.log('║  最適化:                                            ║');
  console.log('║   • Nagle無効 (TCP_NODELAY)                        ║');
  console.log('║   • 圧縮無効 (perMessageDeflate: false)             ║');
  console.log('║   • バイナリプロトコル (24バイト/メッセージ)            ║');
  console.log('║   • 即時ブロードキャスト (バッファなし)               ║');
  console.log('╚══════════════════════════════════════════════════════╝');
  console.log('');
  console.log('  Ctrl+C で停止');
  console.log('');
});

// ===== クリーンシャットダウン =====
process.on('SIGINT', () => {
  console.log('\nShutting down...');
  clearInterval(pingTimer);

  // 全クライアントに通知
  for (const [ws] of clients) {
    try {
      ws.close(1001, 'Server shutting down');
    } catch (e) {}
  }

  wss.close(() => {
    httpServer.close(() => {
      console.log('Server stopped.');
      process.exit(0);
    });
  });

  // 3秒後に強制終了
  setTimeout(() => process.exit(0), 3000);
});

function log(msg) {
  const ts = new Date().toLocaleTimeString('ja-JP', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  console.log(`${ts} ${msg}`);
}
