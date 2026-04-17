#!/usr/bin/env python3
"""
CFMS-5T データ送信スクリプト — .dat ファイル監視 & Firebase 送信

使い方:
  1. pip install watchdog
  2. python cfms_sender.py "C:\\Users\\User\\Desktop\\DATA\\...\\sample.dat"
     → 指定した .dat ファイルを監視し、新しい行を Firebase に送信

  3. python cfms_sender.py --dir "C:\\Users\\User\\Desktop\\DATA"
     → 指定フォルダ内の最新 .dat ファイルを自動検出して監視

  4. python cfms_sender.py --test
     → テストモード（サンプルデータで動作確認）

オプション:
  --interval N    送信間隔（秒）デフォルト 5
  --batch N       一度に送る最大行数 デフォルト 50
"""

import time
import json
import signal
import sys
import os
import threading
import queue
import glob
from datetime import datetime
import urllib.request
import urllib.error

# ===== 設定 =====
FIREBASE_URL = "https://research-tools-board-default-rtdb.firebaseio.com"
FIREBASE_PATH_LIVE = "cfms/live"       # リアルタイム値（最新1件を上書き）
FIREBASE_PATH_LOG  = "cfms/log"        # ログ（追記）
FIREBASE_PATH_META = "cfms/meta"       # メタデータ（ファイル名、カラム情報）

SEND_INTERVAL = 5.0    # Firebase送信間隔（秒）
MAX_BATCH = 50         # 一度に送る最大行数

# .dat ファイルのカラム定義
COLUMNS = [
    "Time", "B_digital_(T)", "B_analog_(T)",
    "I_s", "V_s", "R_s", "V_nv", "R_nv",
    "T_VTI_(K)", "sensor_B_(K)",
    "He_Pot", "2nd_Stage", "Magnet", "Switch",
    "1st_Stage", "Charcoal_Trap", "Hall_T", "Hall_voltage"
]

# 主要カラム（Web に送信する）
KEY_COLUMNS = [
    "Time", "R_nv", "R_s", "sensor_B_(K)", "T_VTI_(K)",
    "B_digital_(T)", "I_s", "V_s", "V_nv",
    "He_Pot", "2nd_Stage", "Magnet"
]

# ===== グローバル変数 =====
running = True
data_queue = queue.Queue(maxsize=500)

# ===== Firebase REST API =====
def firebase_put(path, data, timeout=5):
    url = f"{FIREBASE_URL}/{path}.json"
    req = urllib.request.Request(
        url, data=json.dumps(data).encode('utf-8'),
        method='PUT', headers={'Content-Type': 'application/json'}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status == 200
    except Exception as e:
        print(f"  [Firebase PUT error] {e}")
        return False

def firebase_push(path, data, timeout=5):
    url = f"{FIREBASE_URL}/{path}.json"
    req = urllib.request.Request(
        url, data=json.dumps(data).encode('utf-8'),
        method='POST', headers={'Content-Type': 'application/json'}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status == 200
    except Exception as e:
        print(f"  [Firebase PUSH error] {e}")
        return False

def firebase_delete(path, timeout=5):
    url = f"{FIREBASE_URL}/{path}.json"
    req = urllib.request.Request(url, method='DELETE')
    try:
        urllib.request.urlopen(req, timeout=timeout)
    except:
        pass


# ===== .dat ファイルパーサー =====
def parse_dat_line(line, columns=None):
    """タブ区切りの1行をパースしてdictを返す"""
    parts = line.strip().split('\t')
    if columns is None:
        columns = COLUMNS

    if len(parts) < len(columns):
        return None

    row = {}
    for i, col in enumerate(columns):
        try:
            row[col] = float(parts[i])
        except (ValueError, IndexError):
            row[col] = parts[i] if i < len(parts) else None
    return row


def extract_key_data(row):
    """送信用に主要カラムだけ抽出"""
    data = {}
    for col in KEY_COLUMNS:
        if col in row and row[col] is not None:
            data[col] = row[col]
    data["sent_at"] = int(time.time() * 1000)
    return data


# ===== ファイル監視 =====
def find_latest_dat(directory):
    """ディレクトリ内の最新 .dat ファイルを見つける"""
    pattern = os.path.join(directory, "**", "*.dat")
    files = glob.glob(pattern, recursive=True)
    if not files:
        return None
    return max(files, key=os.path.getmtime)


def tail_file(filepath, start_line=0):
    """ファイルの新しい行を読み取る（tail -f 的な動作）"""
    try:
        with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
            lines = f.readlines()
            return lines[start_line:], len(lines)
    except Exception as e:
        print(f"  [ファイル読み取りエラー] {e}")
        return [], start_line


def file_watcher_thread(filepath):
    """ファイルを定期的にチェックして新しい行をキューに送る"""
    global running

    print(f"  [監視] {filepath}")
    print(f"  [監視] ファイルサイズ: {os.path.getsize(filepath):,} bytes")

    # ヘッダー行を読み取り
    columns = COLUMNS
    with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
        header_line = f.readline().strip()
        if header_line:
            detected_cols = header_line.split('\t')
            if len(detected_cols) >= 5:
                columns = detected_cols
                print(f"  [監視] カラム検出: {len(columns)} 列")
                print(f"  [監視] カラム: {', '.join(columns[:8])}...")

    # 既存データの行数をカウント（最後の N 行だけ送信）
    with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
        total_lines = sum(1 for _ in f)

    # 最初は最新500行から開始（過去データも表示）
    initial_start = max(1, total_lines - 500)  # 1 = ヘッダースキップ
    current_line = initial_start

    print(f"  [監視] 総行数: {total_lines:,} 行")
    print(f"  [監視] 行 {initial_start} から読み取り開始")

    # メタデータ送信
    firebase_put(FIREBASE_PATH_META, {
        "filename": os.path.basename(filepath),
        "columns": columns,
        "total_lines": total_lines,
        "started_at": int(time.time() * 1000),
    })

    while running:
        try:
            new_lines, new_total = tail_file(filepath, current_line)

            if new_lines:
                count = 0
                for line in new_lines:
                    line = line.strip()
                    if not line:
                        continue
                    row = parse_dat_line(line, columns)
                    if row:
                        data = extract_key_data(row)
                        try:
                            data_queue.put_nowait(data)
                            count += 1
                        except queue.Full:
                            try:
                                data_queue.get_nowait()
                            except:
                                pass
                            data_queue.put_nowait(data)
                            count += 1

                current_line = new_total
                if count > 0:
                    print(f"  [監視] +{count} 行 (計 {new_total:,} 行)")

            time.sleep(2)  # 2秒ごとにファイルチェック

        except Exception as e:
            print(f"  [監視エラー] {e}")
            time.sleep(5)


# ===== Firebase 送信スレッド =====
def firebase_sender_thread():
    """データキューからFirebaseへバッチ送信"""
    global running

    while running:
        try:
            batch = []
            # キューから最大 MAX_BATCH 件取得
            try:
                while len(batch) < MAX_BATCH:
                    data = data_queue.get(timeout=SEND_INTERVAL)
                    if data is None:
                        break
                    batch.append(data)
            except queue.Empty:
                pass

            if not batch:
                continue

            # 最新データを live に PUT
            latest = batch[-1]
            firebase_put(FIREBASE_PATH_LIVE, latest)

            # 全データを log に PUSH（バッチ送信）
            for data in batch:
                firebase_push(FIREBASE_PATH_LOG, data)

            ts = datetime.now().strftime("%H:%M:%S")
            temp = latest.get("sensor_B_(K)", "?")
            r_nv = latest.get("R_nv", "?")
            if isinstance(temp, float):
                temp = f"{temp:.2f} K"
            if isinstance(r_nv, float):
                r_nv = f"{r_nv:.6f} Ω"
            print(f"  [{ts}] 送信 {len(batch)} 件 | T={temp} | R_nv={r_nv}")

        except Exception as e:
            print(f"  [送信エラー] {e}")
            time.sleep(2)


# ===== テストモード =====
def test_mode():
    """サンプルデータでテスト"""
    import random

    print("\n  テストモードで動作中（ダミーデータを送信）")

    # メタデータ送信
    firebase_put(FIREBASE_PATH_META, {
        "filename": "TEST_300K_to_2K.dat",
        "columns": COLUMNS,
        "total_lines": 0,
        "started_at": int(time.time() * 1000),
    })

    temp = 300.0
    count = 0

    while running:
        # 温度を徐々に下げる
        temp -= random.uniform(0.3, 1.5)
        if temp < 2.0:
            temp = 300.0  # リセット

        r_nv = 0.02 + 0.001 * (300 - temp) + random.gauss(0, 0.0001)
        r_s = 95.0 + random.gauss(0, 0.1)

        data = {
            "Time": time.time(),
            "R_nv": round(r_nv, 8),
            "R_s": round(r_s, 4),
            "sensor_B_(K)": round(temp, 4),
            "T_VTI_(K)": round(temp + random.gauss(0, 0.5), 4),
            "B_digital_(T)": round(random.gauss(0, 0.001), 6),
            "I_s": 0.006,
            "V_s": round(r_s * 0.006, 6),
            "V_nv": round(r_nv * 0.006, 8),
            "He_Pot": round(9.5 + random.gauss(0, 0.2), 3),
            "2nd_Stage": round(3.1 + random.gauss(0, 0.05), 3),
            "Magnet": round(3.1 + random.gauss(0, 0.05), 3),
            "sent_at": int(time.time() * 1000),
        }

        firebase_put(FIREBASE_PATH_LIVE, data)
        firebase_push(FIREBASE_PATH_LOG, data)

        count += 1
        ts = datetime.now().strftime("%H:%M:%S")
        print(f"  [{ts}] #{count:>5}  T={temp:.2f} K  R_nv={r_nv:.6f} Ω")

        time.sleep(3)


# ===== シグナルハンドラ =====
def signal_handler(sig, frame):
    global running
    print("\n停止中...")
    running = False

signal.signal(signal.SIGINT, signal_handler)


# ===== メイン =====
def main():
    global running, SEND_INTERVAL, MAX_BATCH

    print("=" * 60)
    print("  CFMS-5T データ送信スクリプト (v1.0)")
    print("=" * 60)

    # オプション解析
    args = sys.argv[1:]
    filepath = None
    directory = None
    test = False

    i = 0
    while i < len(args):
        if args[i] == "--test":
            test = True
        elif args[i] == "--dir":
            i += 1
            if i < len(args):
                directory = args[i]
        elif args[i] == "--interval":
            i += 1
            if i < len(args):
                SEND_INTERVAL = float(args[i])
        elif args[i] == "--batch":
            i += 1
            if i < len(args):
                MAX_BATCH = int(args[i])
        elif not args[i].startswith("--"):
            filepath = args[i]
        i += 1

    print(f"  Firebase:     {FIREBASE_URL}")
    print(f"  送信間隔:     {SEND_INTERVAL} 秒")
    print(f"  最大バッチ:   {MAX_BATCH} 行")
    print(f"  停止:         Ctrl+C")
    print("=" * 60)

    if test:
        # 起動時に古いデータをクリア
        firebase_delete("cfms/command")
        test_mode()
        return

    # ファイルパスの決定
    if not filepath and directory:
        filepath = find_latest_dat(directory)
        if filepath:
            print(f"\n  最新ファイル検出: {filepath}")
        else:
            print(f"\n  [エラー] {directory} に .dat ファイルが見つかりません")
            return

    if not filepath:
        print("\n  使い方:")
        print('    python cfms_sender.py "C:\\path\\to\\data.dat"')
        print('    python cfms_sender.py --dir "C:\\path\\to\\data_folder"')
        print('    python cfms_sender.py --test')
        return

    if not os.path.exists(filepath):
        print(f"\n  [エラー] ファイルが見つかりません: {filepath}")
        return

    print(f"\n  監視ファイル: {filepath}")
    print(f"  ファイルサイズ: {os.path.getsize(filepath):,} bytes")

    # 起動時に古いコマンドをクリア
    firebase_delete("cfms/command")
    print("  [初期化] 古いコマンドをクリア")

    # スレッド起動
    watcher = threading.Thread(target=file_watcher_thread, args=(filepath,), daemon=True)
    watcher.start()

    sender = threading.Thread(target=firebase_sender_thread, daemon=True)
    sender.start()

    print("  [スレッド] ファイル監視スレッド 起動")
    print("  [スレッド] Firebase送信スレッド 起動")
    print("\n  監視中... (Ctrl+C で停止)\n")

    # メインスレッドは待機
    while running:
        time.sleep(1)

    data_queue.put(None)
    print("終了しました。")


if __name__ == "__main__":
    main()
