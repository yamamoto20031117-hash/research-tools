#!/usr/bin/env python3
"""
Keithley 2400 SourceMeter リアルタイムモニター — ラボPC用送信スクリプト

使い方:
  1. pip install pyvisa pyvisa-py pyserial websocket-client
  2. Keithley 2400 を USB or GPIB でラボPCに接続
  3. python dmm_sender.py で実行（まずテストモードで動作確認）
  4. 接続確認後、--live オプションで実機モードに切り替え

コマンド:
  python dmm_sender.py               # テストモード（ダミーデータ、WebSocket同期）
  python dmm_sender.py --live        # 実機モード（Keithley 2400 に接続）
  python dmm_sender.py --list        # 接続可能なVISAデバイス一覧を表示
  python dmm_sender.py --ws-only     # WebSocketのみ（Firebase無効）
  python dmm_sender.py --firebase-only  # Firebase のみ（WebSocket無効）
  python dmm_sender.py --ws-url ws://192.168.1.10:8765  # WebSocketサーバー指定

同期モード:
  デフォルト: WebSocket (超低レイテンシ) + Firebase (バックアップ/ログ)
  --ws-only:  WebSocket のみ (最速、LAN内推奨)
  --firebase-only: Firebase のみ (従来互換)
"""

import time
import json
import signal
import sys
import os
import threading
import queue
import struct
from datetime import datetime
import urllib.request
import urllib.error

# ===== 設定 =====
FIREBASE_URL = "https://research-tools-board-default-rtdb.firebaseio.com"
FIREBASE_PATH_LIVE = "dmm/live"       # リアルタイム値（最新1件を上書き）
FIREBASE_PATH_LOG = "dmm/log"         # ログ（追記）
INTERVAL = 1.0                         # 測定間隔（秒）デフォルト値
WS_URL = "ws://localhost:8765"         # WebSocket sync server URL

# GPIB接続の場合: "GPIB0::24::INSTR" (アドレス24が一般的)
# USB接続の場合: 自動検出を試みる
DMM_ADDRESS = ""  # 空欄なら自動検出

# コマンドライン引数で上書き
for i, arg in enumerate(sys.argv):
    if arg == "--ws-url" and i + 1 < len(sys.argv):
        WS_URL = sys.argv[i + 1]

USE_WEBSOCKET = "--firebase-only" not in sys.argv
USE_FIREBASE = "--ws-only" not in sys.argv


# ===== スレッド間共有変数 =====
interval = INTERVAL        # 実行時の間隔（Webから変更可能）
auto_stop_time = 0         # 0 = 無制限
running = True
output_on = False          # OUTPUT状態
command_queue = queue.Queue()   # コマンド受信キュー（command_thread → main）
data_queue = queue.Queue(maxsize=5000)  # データ送信キュー（main → sender_thread）
ws_data_queue = queue.Queue(maxsize=5000)  # WebSocket送信キュー
smu_lock = threading.Lock()    # Keithleyシリアル通信の排他制御
last_source_config = {}        # 前回のソース設定（再設定スキップ用）
ws_connection = None           # WebSocket接続オブジェクト
ws_connected = False           # WebSocket接続状態


# ===== Firebase REST API（タイムアウト短縮） =====
def firebase_put(path, data, timeout=3):
    """Firebase に PUT（上書き）"""
    url = f"{FIREBASE_URL}/{path}.json"
    req = urllib.request.Request(
        url, data=json.dumps(data).encode('utf-8'),
        method='PUT', headers={'Content-Type': 'application/json'}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status == 200
    except Exception:
        return False

def firebase_push(path, data, timeout=3):
    """Firebase に POST（追記）"""
    url = f"{FIREBASE_URL}/{path}.json"
    req = urllib.request.Request(
        url, data=json.dumps(data).encode('utf-8'),
        method='POST', headers={'Content-Type': 'application/json'}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status == 200
    except Exception:
        return False

def firebase_get(path, timeout=3):
    """Firebase から GET"""
    url = f"{FIREBASE_URL}/{path}.json"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return json.loads(resp.read().decode('utf-8'))
    except:
        return None

def firebase_delete(path, timeout=3):
    """Firebase から DELETE"""
    url = f"{FIREBASE_URL}/{path}.json"
    req = urllib.request.Request(url, method='DELETE')
    try:
        urllib.request.urlopen(req, timeout=timeout)
    except:
        pass

def update_output_status(on):
    """OUTPUT状態をFirebaseに送信"""
    firebase_put("dmm/status", {"output": on, "time": int(time.time()*1000)})


# ===== RS-232 ユーティリティ =====
def flush_buffer(smu):
    """RS-232入力バッファをクリア"""
    if not smu:
        return
    try:
        if smu.bytes_in_buffer > 0:
            smu.read_bytes(smu.bytes_in_buffer)
    except:
        pass

def safe_write(smu, cmd, delay=0.1):
    """エラークリア + バッファクリア付きで安全にSCPIコマンドを送信"""
    if not smu:
        return
    flush_buffer(smu)
    try:
        smu.write(cmd)
    except Exception as e:
        print(f"  [SCPI write error] {cmd} -> {e}")
        time.sleep(0.5)
        flush_buffer(smu)
        try:
            smu.write("*CLS")
            time.sleep(0.3)
            smu.write(cmd)
        except Exception as e2:
            print(f"  [SCPI retry failed] {cmd} -> {e2}")
    time.sleep(delay)


# ===== WebSocket 接続・送信 =====
def ws_connect():
    """WebSocketサーバーに接続"""
    global ws_connection, ws_connected
    try:
        import websocket
        ws = websocket.WebSocket()
        ws.settimeout(5)
        ws.connect(WS_URL, suppress_origin=True)
        # TCP_NODELAY for minimum latency
        ws.sock.setsockopt(6, 1, 1)  # IPPROTO_TCP, TCP_NODELAY
        ws.send(json.dumps({"type": "hello", "role": "sender"}))
        resp = ws.recv()
        welcome = json.loads(resp)
        print(f"  [WS] 接続成功 (ID #{welcome.get('id', '?')})")
        ws_connection = ws
        ws_connected = True
        return ws
    except ImportError:
        print("  [WS] websocket-client がインストールされていません")
        print("       pip install websocket-client")
        return None
    except Exception as e:
        print(f"  [WS] 接続失敗: {e}")
        ws_connected = False
        return None


def ws_sender_thread():
    """WebSocketキューからバイナリデータを送信（最速パス）"""
    global ws_connection, ws_connected
    reconnect_wait = 1

    while running:
        # 接続がなければ再接続
        if not ws_connected or ws_connection is None:
            ws = ws_connect()
            if ws is None:
                time.sleep(min(reconnect_wait, 10))
                reconnect_wait = min(reconnect_wait * 2, 30)
                continue
            reconnect_wait = 1

        try:
            data = ws_data_queue.get(timeout=1)
            if data is None:
                break

            # バイナリ24バイト: [timestamp_f64, voltage_f64, current_f64]
            binary = struct.pack('<ddd', data['time'], data['voltage'], data['current'])
            ws_connection.send_binary(binary)
            ws_data_queue.task_done()

        except queue.Empty:
            continue
        except Exception as e:
            print(f"  [WS] 送信エラー: {e}")
            ws_connected = False
            try:
                ws_connection.close()
            except:
                pass
            ws_connection = None


def ws_command_listener_thread():
    """WebSocketサーバーからコマンドを受信"""
    global ws_connection, ws_connected, auto_stop_time, interval, output_on

    while running:
        if not ws_connected or ws_connection is None:
            time.sleep(1)
            continue

        try:
            ws_connection.settimeout(1)
            msg_raw = ws_connection.recv()
            if not msg_raw:
                continue

            # バイナリメッセージは無視 (sender echo はサーバーがフィルタ済み)
            if isinstance(msg_raw, bytes):
                continue

            msg = json.loads(msg_raw)

            if msg.get("type") == "command":
                action = msg.get("action")
                if action:
                    command_queue.put(("WS_CMD", msg))
                    print(f"  [WS] コマンド受信: {action}")

        except Exception:
            # タイムアウトは正常
            continue


# ===== ローカルCSVバックアップ =====
local_csv_path = None

def init_local_csv():
    """測定開始時にローカルCSVファイルを作成"""
    global local_csv_path
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    local_csv_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), f"dmm_log_{ts}.csv")
    with open(local_csv_path, 'w') as f:
        f.write("time_ms,datetime,voltage,current\n")
    print(f"  [CSV] ローカルバックアップ: {local_csv_path}")

def append_local_csv(data):
    """データをローカルCSVに追記（Firebaseに依存しない確実な保存）"""
    if local_csv_path is None:
        return
    try:
        ts = datetime.fromtimestamp(data["time"]/1000).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        with open(local_csv_path, 'a') as f:
            f.write(f"{data['time']},{ts},{data['voltage']},{data['current']}\n")
    except Exception:
        pass

# ===== Firebase データ送信スレッド =====
def firebase_sender_thread():
    """データキューからFirebaseへ非同期送信（バッチ対応）"""
    batch = []
    BATCH_SIZE = 10
    BATCH_TIMEOUT = 2.0

    while running:
        try:
            data = data_queue.get(timeout=BATCH_TIMEOUT)
            if data is None:
                # 残りのバッチを送信
                if batch:
                    _send_batch(batch)
                break
            batch.append(data)
            # ローカルCSVにも保存（確実なバックアップ）
            append_local_csv(data)
            data_queue.task_done()

            if len(batch) >= BATCH_SIZE:
                _send_batch(batch)
                batch = []
        except queue.Empty:
            # タイムアウト: 溜まったバッチを送信
            if batch:
                _send_batch(batch)
                batch = []
        except Exception as e:
            print(f"  [Firebase] 送信エラー: {e}")

def _send_batch(batch):
    """バッチデータをFirebaseに送信"""
    if not batch:
        return
    # 最新値をliveに送信
    firebase_put(FIREBASE_PATH_LIVE, batch[-1])
    # ログはバッチでまとめてPATCH
    patch_data = {}
    for d in batch:
        key = str(d["time"])
        patch_data[key] = d
    try:
        url = f"{FIREBASE_URL}/{FIREBASE_PATH_LOG}.json"
        req = urllib.request.Request(
            url, data=json.dumps(patch_data).encode('utf-8'),
            method='PATCH', headers={'Content-Type': 'application/json'}
        )
        urllib.request.urlopen(req, timeout=10)
    except Exception as e:
        print(f"  [Firebase] バッチ送信エラー ({len(batch)}件): {e}")


# ===== Firebase コマンド監視スレッド =====
def firebase_command_thread(smu):
    """Firebaseのコマンドを定期的にチェック"""
    global auto_stop_time, interval, output_on

    while running:
        try:
            # コマンドチェック
            cmd = firebase_get("dmm/command")
            if cmd and cmd.get("action"):
                action = cmd["action"]
                firebase_delete("dmm/command")

                if action == "OUTPUT_OFF":
                    print("\n  *** Web: OUTPUT OFF ***")
                    with smu_lock:
                        safe_write(smu, ":OUTP OFF", 0.2)
                    auto_stop_time = 0
                    output_on = False
                    update_output_status(False)
                    command_queue.put(("OFF", None))

                elif action == "OUTPUT_ON":
                    print("\n  *** Web: OUTPUT ON ***")
                    with smu_lock:
                        safe_write(smu, ":OUTP ON", 0.3)
                    output_on = True
                    update_output_status(True)
                    command_queue.put(("ON", None))

                elif action == "SET_INTERVAL":
                    new_interval = float(cmd.get("interval", 1.0))
                    interval = max(0.1, min(new_interval, 60.0))
                    print(f"\n  *** Web: 測定間隔 -> {interval} 秒 ***")

                elif action == "SOURCE_START":
                    global last_source_config
                    src_mode = cmd.get("mode", "CURR")
                    value = float(cmd.get("value", 0))
                    compliance = float(cmd.get("compliance", 21))
                    duration = float(cmd.get("duration", 0))

                    new_config = {"mode": src_mode, "value": value, "compliance": compliance}
                    need_reconfig = (new_config != last_source_config)

                    with smu_lock:
                        if need_reconfig:
                            print(f"\n  *** Web: SOURCE START (設定変更) ***")
                            configure_source(smu, src_mode, value, compliance)
                            last_source_config = new_config
                        else:
                            print(f"\n  *** Web: SOURCE START (再開) ***")
                        safe_write(smu, ":OUTP ON", 0.3)

                    output_on = True
                    update_output_status(True)

                    if duration > 0:
                        auto_stop_time = time.time() + duration
                        print(f"  自動停止: {datetime.fromtimestamp(auto_stop_time).strftime('%H:%M:%S')}")
                    else:
                        auto_stop_time = 0

                    command_queue.put(("ON", None))

            # タイマー自動停止チェック
            if auto_stop_time > 0 and time.time() >= auto_stop_time:
                print("\n  *** タイマー満了: OUTPUT OFF ***")
                with smu_lock:
                    safe_write(smu, ":OUTP OFF", 0.2)
                auto_stop_time = 0
                output_on = False
                update_output_status(False)
                command_queue.put(("OFF", None))

        except Exception as e:
            print(f"  [Command thread error] {e}")

        # コマンドチェック間隔（OUTPUT OFF時は1秒、ON時は2秒）
        sleep_time = 1.0 if not output_on else 2.0
        time.sleep(sleep_time)


def configure_source(smu, mode, value, compliance):
    """ソースモードと値を設定"""
    if not smu:
        return

    safe_write(smu, ":OUTP OFF", 0.15)
    safe_write(smu, "*CLS", 0.1)

    if mode == "CURR":
        safe_write(smu, ":SOUR:FUNC CURR", 0.1)
        safe_write(smu, ":SOUR:CURR:RANG:AUTO ON", 0.1)
        safe_write(smu, f":SOUR:CURR {value}", 0.1)
        safe_write(smu, f":SENS:VOLT:PROT {compliance}", 0.1)
    elif mode == "VOLT":
        safe_write(smu, ":SOUR:FUNC VOLT", 0.1)
        safe_write(smu, ":SOUR:VOLT:RANG:AUTO ON", 0.1)
        safe_write(smu, f":SOUR:VOLT {value}", 0.1)
        safe_write(smu, f":SENS:CURR:PROT {compliance}", 0.1)

    safe_write(smu, ":SENS:FUNC:CONC ON", 0.1)
    safe_write(smu, ":SENS:FUNC 'VOLT:DC','CURR:DC'", 0.1)
    safe_write(smu, ":FORM:ELEM VOLT,CURR", 0.1)


# ===== Keithley 2400 接続 =====
def list_visa_resources():
    """接続可能なVISAデバイス一覧を表示"""
    try:
        import pyvisa
        rm = pyvisa.ResourceManager()
        resources = rm.list_resources()
        if resources:
            print("検出されたVISAリソース:")
            for r in resources:
                print(f"  - {r}")
                try:
                    inst = rm.open_resource(r)
                    inst.timeout = 3000
                    idn = inst.query("*IDN?").strip()
                    print(f"    -> {idn}")
                    inst.close()
                except:
                    print(f"    -> (IDN取得不可)")
        else:
            print("VISAデバイスが見つかりません")
    except ImportError:
        print("pyvisa がインストールされていません")
        print("  pip install pyvisa pyvisa-py pyserial")


def connect_keithley():
    """Keithley 2400 に接続（自動検出対応）"""
    import pyvisa
    rm = pyvisa.ResourceManager()
    resources = rm.list_resources()
    print(f"検出されたVISAリソース: {resources}")

    smu = None

    if DMM_ADDRESS:
        try:
            smu = rm.open_resource(DMM_ADDRESS)
            print(f"  {DMM_ADDRESS} に接続")
        except Exception:
            print(f"  {DMM_ADDRESS} に接続できません。自動検出に切り替え...")

    if not smu:
        print("  シリアルポートを自動検出中...")
        serial_resources = [r for r in resources if r.startswith("ASRL")]
        for r in serial_resources:
            try:
                inst = rm.open_resource(r)
                inst.timeout = 5000
                inst.write_termination = '\r'
                inst.read_termination = '\r'
                inst.baud_rate = 9600
                try:
                    inst.read_bytes(inst.bytes_in_buffer) if inst.bytes_in_buffer > 0 else None
                except:
                    pass
                idn = inst.query("*IDN?").strip()
                if "KEITHLEY" in idn.upper() or "2400" in idn:
                    smu = inst
                    print(f"  Keithley 自動検出: {r} -> {idn}")
                    break
                inst.close()
            except:
                try:
                    inst.close()
                except:
                    pass

    if not smu:
        print("Keithley 2400 が見つかりません")
        return None

    smu.timeout = 30000
    smu.write_termination = '\r'
    smu.read_termination = '\r'
    smu.baud_rate = 9600
    smu.data_bits = 8
    smu.stop_bits = pyvisa.constants.StopBits.one
    smu.parity = pyvisa.constants.Parity.none
    smu.flow_control = pyvisa.constants.VI_ASRL_FLOW_NONE

    try:
        smu.read_bytes(smu.bytes_in_buffer) if smu.bytes_in_buffer > 0 else None
    except:
        pass

    idn = smu.query("*IDN?").strip()
    print(f"接続成功: {idn}")

    print("初期設定中...")
    safe_write(smu, "*RST", 2.0)
    safe_write(smu, "*CLS", 0.5)
    safe_write(smu, ":SYST:BEEP:STAT OFF", 0.5)
    safe_write(smu, ":SENS:FUNC:CONC ON", 0.5)
    safe_write(smu, ":SENS:FUNC 'VOLT:DC','CURR:DC'", 0.5)
    safe_write(smu, ":FORM:ELEM VOLT,CURR", 0.5)
    safe_write(smu, ":SOUR:FUNC CURR", 0.5)
    safe_write(smu, ":SOUR:CURR:RANG MIN", 0.5)
    safe_write(smu, ":SOUR:CURR 0", 0.5)

    print("初期設定完了")
    print("  モード: 電圧・電流 同時測定")
    print("  ソース: 0A（待機中）")
    print("  OUTPUT: OFF（Webから制御）")
    update_output_status(False)
    return smu


def read_keithley(smu):
    """Keithley 2400 から電圧・電流を読み取る"""
    flush_buffer(smu)
    try:
        result = smu.query(":READ?")
    except Exception:
        time.sleep(0.5)
        flush_buffer(smu)
        try:
            smu.write("*CLS")
            time.sleep(0.3)
        except:
            pass
        result = smu.query(":MEAS?")
    vals = result.strip().split(',')
    voltage = float(vals[0])
    current = float(vals[1])
    if abs(voltage) > 1e6:
        voltage = 0.0
    if abs(current) > 1e6:
        current = 0.0
    return voltage, current


def read_dummy():
    """テスト用ダミーデータ"""
    import random
    voltage = 3.3 + random.gauss(0, 0.01)
    current = 0.015 + random.gauss(0, 0.0005)
    return voltage, current


# ===== シグナルハンドラ =====
def signal_handler(sig, frame):
    global running
    print("\n停止中...")
    running = False

signal.signal(signal.SIGINT, signal_handler)


# ===== メインループ =====
def main():
    global running, output_on, auto_stop_time

    mode = "test"
    if "--live" in sys.argv:
        mode = "live"
    if "--list" in sys.argv:
        list_visa_resources()
        return

    print("=" * 60)
    print("  Keithley 2400 リアルタイムモニター (v3 WebSocket sync)")
    print("=" * 60)
    print(f"  モード:       {'実機接続' if mode=='live' else 'テスト（ダミーデータ）'}")
    print(f"  WebSocket:    {WS_URL if USE_WEBSOCKET else '無効'}")
    print(f"  Firebase:     {FIREBASE_URL if USE_FIREBASE else '無効'}")
    print(f"  測定間隔:     {INTERVAL} 秒")
    print(f"  停止:         Ctrl+C")
    print("=" * 60)

    smu = None
    if mode == "live":
        retry_wait = 10
        while running:
            try:
                smu = connect_keithley()
                if smu:
                    break
                print(f"\n  Keithley が見つかりません。{retry_wait}秒後に再試行...")
                time.sleep(retry_wait)
            except ImportError:
                print("pyvisa がインストールされていません")
                print("  pip install pyvisa pyvisa-py pyserial")
                return
            except Exception as e:
                print(f"  接続エラー: {e} -- {retry_wait}秒後に再試行...")
                time.sleep(retry_wait)
        if not smu and not running:
            return
    else:
        print("\nテストモードで動作中（ダミーデータを送信）")
        print("実機に接続するには: python dmm_sender.py --live\n")

    # ----- 起動時に古いコマンドをクリア -----
    firebase_delete("dmm/command")
    print("  [初期化] 古いコマンドをクリア")

    # ----- スレッド起動 -----
    if USE_FIREBASE:
        sender = threading.Thread(target=firebase_sender_thread, daemon=True)
        sender.start()
        cmd_thread = threading.Thread(target=firebase_command_thread, args=(smu,), daemon=True)
        cmd_thread.start()
        print("  [スレッド] Firebase送信スレッド 起動")
        print("  [スレッド] Firebaseコマンド監視スレッド 起動")

    if USE_WEBSOCKET:
        ws_sender = threading.Thread(target=ws_sender_thread, daemon=True)
        ws_sender.start()
        ws_cmd = threading.Thread(target=ws_command_listener_thread, daemon=True)
        ws_cmd.start()
        print("  [スレッド] WebSocket送信スレッド 起動")
        print("  [スレッド] WebSocketコマンド監視スレッド 起動")

    # ----- メインループ: 測定のみに集中 -----
    count = 0
    errors = 0

    def fmt_i(i):
        a = abs(i)
        if a < 1e-6: return f"{i*1e9:>8.3f} nA"
        if a < 1e-3: return f"{i*1e6:>8.3f} uA"
        if a < 1:    return f"{i*1e3:>8.4f} mA"
        return f"{i:>8.5f} A"

    def fmt_v(v):
        a = abs(v)
        if a < 1e-3: return f"{v*1e6:>8.2f} uV"
        if a < 1:    return f"{v*1e3:>8.4f} mV"
        return f"{v:>8.5f} V"

    print("\n  OUTPUT OFF -- Webからの指令を待機中...")

    while running:
        loop_start = time.time()
        try:
            # コマンドスレッドからの通知を確認（ノンブロッキング）
            try:
                while True:
                    cmd_msg, cmd_data = command_queue.get_nowait()
                    if cmd_msg == "OFF":
                        output_on = False
                        print("\n  OUTPUT OFF -- 測定停止")
                    elif cmd_msg == "ON":
                        output_on = True
                        init_local_csv()
                        print("\n  OUTPUT ON -- 測定開始")
                    elif cmd_msg == "WS_CMD":
                        # WebSocket経由のコマンド処理
                        action = cmd_data.get("action", "")
                        if action == "OUTPUT_OFF":
                            print("\n  *** WS: OUTPUT OFF ***")
                            with smu_lock:
                                if smu: safe_write(smu, ":OUTP OFF", 0.2)
                            auto_stop_time = 0
                            output_on = False
                            if USE_FIREBASE: update_output_status(False)
                        elif action == "SOURCE_START":
                            src_mode = cmd_data.get("mode", "CURR")
                            value = float(cmd_data.get("value", 0))
                            compliance = float(cmd_data.get("compliance", 21))
                            duration = float(cmd_data.get("duration", 0))
                            with smu_lock:
                                if smu: configure_source(smu, src_mode, value, compliance)
                                if smu: safe_write(smu, ":OUTP ON", 0.3)
                            output_on = True
                            if duration > 0:
                                auto_stop_time = time.time() + duration
                            if USE_FIREBASE: update_output_status(True)
                            print(f"\n  *** WS: SOURCE START ({src_mode}) ***")
                        elif action == "SET_INTERVAL":
                            interval = max(0.1, min(float(cmd_data.get("interval", 1.0)), 60.0))
                            print(f"\n  *** WS: 測定間隔 -> {interval} 秒 ***")
            except queue.Empty:
                pass

            # OUTPUT OFF 時はスキップ
            if not output_on:
                time.sleep(max(0.05, interval - (time.time() - loop_start)))
                continue

            # === 測定（これだけがメインスレッドの仕事） ===
            if mode == "live" and smu:
                with smu_lock:
                    voltage, current = read_keithley(smu)
            else:
                voltage, current = read_dummy()

            now = int(time.time() * 1000)
            data = {
                "time": now,
                "voltage": round(voltage, 8),
                "current": round(current, 8),
            }

            # データキューに投入（送信スレッドが非同期で送信）
            if USE_FIREBASE:
                try:
                    data_queue.put_nowait(data)
                except queue.Full:
                    try: data_queue.get_nowait()
                    except: pass
                    data_queue.put_nowait(data)

            if USE_WEBSOCKET:
                try:
                    ws_data_queue.put_nowait(data)
                except queue.Full:
                    try: ws_data_queue.get_nowait()
                    except: pass
                    ws_data_queue.put_nowait(data)

            count += 1
            ts = datetime.now().strftime("%H:%M:%S")

            timer_str = ""
            if auto_stop_time > 0:
                remain = max(0, int(auto_stop_time - time.time()))
                m, s = divmod(remain, 60)
                timer_str = f"  T-{m:02d}:{s:02d}"

            print(f"[{ts}] #{count:>5}  {fmt_v(voltage)}  {fmt_i(current)}{timer_str}")

            errors = 0

        except Exception as e:
            errors += 1
            print(f"  [エラー #{errors}] {e}")
            if errors > 10:
                print("  連続エラー。再接続...")
                if mode == "live" and smu:
                    try:
                        smu.close()
                        smu = connect_keithley()
                        errors = 0
                    except:
                        pass

        # ループ時間を差し引いて残りだけ待つ
        elapsed = time.time() - loop_start
        wait = max(0.01, interval - elapsed)
        time.sleep(wait)

    # ----- クリーンアップ -----
    data_queue.put(None)  # 送信スレッドに終了通知
    if smu:
        try:
            smu.write(":OUTP OFF")
            time.sleep(0.3)
            smu.write(":SYST:LOC")
            time.sleep(0.3)
            smu.close()
            print("Keithley 2400 切断完了")
        except:
            pass
    print("終了しました。")


if __name__ == "__main__":
    main()
