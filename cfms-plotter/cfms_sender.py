#!/usr/bin/env python3
"""
CFMS-5T データ自動送信スクリプト — フォルダ監視 & Firebase 送信

CFMS PCの DATA フォルダを監視し、新しい .dat ファイルを検出したら
自動でパースして Firebase に送信する。

使い方:
  python cfms_sender.py                         # デフォルト (C:\\Users\\User\\Desktop\\DATA)
  python cfms_sender.py "D:\\MyData"             # フォルダ指定
  python cfms_sender.py --test                   # テストモード（ダミーファイル生成）

CFMS PCセットアップ:
  1. Python 3 をインストール（python.org → Add to PATH にチェック）
  2. このファイルをデスクトップに置く
  3. コマンドプロンプトで: python cfms_sender.py
  4. 初回は既存ファイルをスキャンして送信（時間がかかる場合あり）
  5. 以降は新しいファイルが追加されたら自動送信
"""

import time
import json
import signal
import sys
import os
import hashlib
from datetime import datetime
import urllib.request
import urllib.error

# ===== 設定 =====
FIREBASE_URL = "https://research-tools-board-default-rtdb.firebaseio.com"
DEFAULT_WATCH_DIR = r"C:\Users\User\Desktop\DATA"
SCAN_INTERVAL = 10       # フォルダスキャン間隔（秒）
MAX_ROWS_PER_FILE = 20000  # 1ファイルあたり最大行数

# 送信するカラム（データ量を抑える）
KEY_COLUMNS = [
    "Time", "R_nv", "R_s", "sensor_B_(K)", "T_VTI_(K)",
    "B_digital_(T)", "I_s", "V_s", "V_nv"
]

running = True


# ===== Firebase REST API =====
def firebase_put(path, data, timeout=30):
    url = f"{FIREBASE_URL}/{path}.json"
    payload = json.dumps(data).encode('utf-8')
    req = urllib.request.Request(
        url, data=payload,
        method='PUT', headers={'Content-Type': 'application/json'}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status == 200
    except Exception as e:
        print(f"  [Firebase PUT error] {e}")
        return False

def firebase_get(path, timeout=10):
    url = f"{FIREBASE_URL}/{path}.json"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return json.loads(resp.read().decode('utf-8'))
    except:
        return None

def firebase_delete(path, timeout=10):
    url = f"{FIREBASE_URL}/{path}.json"
    req = urllib.request.Request(url, method='DELETE')
    try:
        urllib.request.urlopen(req, timeout=timeout)
    except:
        pass


# ===== .dat ファイルパーサー =====
def parse_dat_file(filepath):
    """タブ区切り .dat ファイルをパースしてヘッダーとデータを返す"""
    try:
        with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
            lines = f.readlines()
    except Exception as e:
        print(f"  [読み取りエラー] {filepath}: {e}")
        return None, None

    if len(lines) < 2:
        return None, None

    headers = lines[0].strip().split('\t')
    data = []

    for i in range(1, min(len(lines), MAX_ROWS_PER_FILE + 1)):
        line = lines[i].strip()
        if not line:
            continue
        parts = line.split('\t')
        row = {}
        for j, col in enumerate(headers):
            if j >= len(parts):
                break
            if col in KEY_COLUMNS:
                try:
                    row[col] = float(parts[j])
                except ValueError:
                    pass
        if row:
            data.append(row)

    return headers, data


def get_file_hash(filepath):
    """ファイルのサイズと更新日時からハッシュを生成（高速）"""
    try:
        stat = os.stat(filepath)
        return f"{stat.st_size}_{int(stat.st_mtime)}"
    except:
        return None


def sanitize_key(name):
    """Firebase キーに使えない文字を置換"""
    # Firebase は . $ # [ ] / を禁止
    for ch in '.#$[]/ ':
        name = name.replace(ch, '_')
    return name


# ===== ファイル送信 =====
def send_file(filepath, file_key):
    """1つの .dat ファイルをパースして Firebase に送信"""
    basename = os.path.basename(filepath)
    relpath = filepath  # フルパスを記録

    print(f"\n  --- {basename} ---")
    print(f"  パース中...")

    headers, data = parse_dat_file(filepath)
    if not data:
        print(f"  [スキップ] データなし: {basename}")
        return False

    print(f"  {len(data):,} 行パース完了")

    # データが大きい場合は分割送信
    # Firebase は 1リクエスト最大 ~16MB
    # 1行あたり約 100 bytes → 10000行で ~1MB → 問題なし
    chunk_size = 5000
    total_chunks = (len(data) + chunk_size - 1) // chunk_size

    # メタデータ送信
    meta = {
        "filename": basename,
        "path": relpath,
        "columns": headers,
        "key_columns": KEY_COLUMNS,
        "total_rows": len(data),
        "chunks": total_chunks,
        "uploaded_at": int(time.time() * 1000),
        "file_hash": get_file_hash(filepath),
    }

    # データのサマリー
    if data:
        temps = [d.get("sensor_B_(K)", 0) for d in data if "sensor_B_(K)" in d]
        if temps:
            meta["temp_min"] = round(min(temps), 2)
            meta["temp_max"] = round(max(temps), 2)
        rnvs = [d.get("R_nv", 0) for d in data if "R_nv" in d]
        if rnvs:
            meta["rnv_min"] = rnvs[0]
            meta["rnv_max"] = rnvs[-1]

    print(f"  メタデータ送信中...")
    firebase_put(f"cfms/files/{file_key}/meta", meta)

    # データ送信（チャンクごと）
    for i in range(total_chunks):
        chunk = data[i * chunk_size : (i + 1) * chunk_size]
        print(f"  チャンク {i+1}/{total_chunks} 送信中 ({len(chunk)} 行)...")
        ok = firebase_put(f"cfms/files/{file_key}/data/{i}", chunk, timeout=60)
        if not ok:
            print(f"  [エラー] チャンク {i+1} 送信失敗")
            return False

    # ファイル一覧に追加
    firebase_put(f"cfms/file_list/{file_key}", {
        "filename": basename,
        "rows": len(data),
        "temp_range": f"{meta.get('temp_min','?')} - {meta.get('temp_max','?')} K",
        "uploaded_at": meta["uploaded_at"],
    })

    print(f"  完了! {len(data):,} 行送信")
    return True


# ===== フォルダスキャン =====
def scan_folder(watch_dir, known_files):
    """フォルダを再帰スキャンして新しい/更新された .dat ファイルを検出"""
    new_files = []

    for root, dirs, files in os.walk(watch_dir):
        for fname in files:
            if not fname.lower().endswith('.dat'):
                continue
            fpath = os.path.join(root, fname)
            fhash = get_file_hash(fpath)
            if fhash and known_files.get(fpath) != fhash:
                new_files.append(fpath)
                known_files[fpath] = fhash

    return new_files


# ===== コントロール（On/Off） =====
def check_enabled():
    """Firebase の制御フラグを確認"""
    try:
        ctrl = firebase_get("cfms/control")
        if ctrl and ctrl.get("enabled") == False:
            return False
    except:
        pass
    return True  # デフォルトは ON


def update_status(status_text, file_count=0):
    """ステータスを Firebase に送信"""
    firebase_put("cfms/sender_status", {
        "status": status_text,
        "files_sent": file_count,
        "last_update": int(time.time() * 1000),
    })


# ===== シグナルハンドラ =====
def signal_handler(sig, frame):
    global running
    print("\n停止中...")
    running = False

signal.signal(signal.SIGINT, signal_handler)


# ===== テストモード =====
def test_mode():
    """テスト用: ダミーの .dat ファイルを生成して送信テスト"""
    import random

    print("\n  テストモード: ダミーデータを Firebase に送信\n")

    # テストデータ生成
    headers = KEY_COLUMNS[:]
    data = []
    temp = 300.0
    for i in range(100):
        temp -= random.uniform(1, 5)
        if temp < 2:
            temp = 2
        data.append({
            "Time": 60000 + i * 7,
            "R_nv": round(0.02 + 0.0001 * (300 - temp) + random.gauss(0, 0.0001), 8),
            "R_s": round(95 + random.gauss(0, 0.1), 4),
            "sensor_B_(K)": round(temp, 4),
            "T_VTI_(K)": round(temp + random.gauss(0, 0.3), 4),
            "B_digital_(T)": round(random.gauss(0, 0.0003), 6),
            "I_s": 0.006,
            "V_s": round(0.57 + random.gauss(0, 0.001), 6),
            "V_nv": round(0.00012 + random.gauss(0, 0.000001), 8),
        })

    file_key = "TEST_300K_to_2K"

    meta = {
        "filename": "TEST_300K_to_2K.dat",
        "path": "test",
        "columns": headers,
        "key_columns": KEY_COLUMNS,
        "total_rows": len(data),
        "chunks": 1,
        "uploaded_at": int(time.time() * 1000),
        "file_hash": "test_" + str(int(time.time())),
        "temp_min": 2.0,
        "temp_max": 300.0,
    }

    print(f"  メタデータ送信...")
    firebase_put(f"cfms/files/{file_key}/meta", meta)
    print(f"  データ送信 ({len(data)} 行)...")
    firebase_put(f"cfms/files/{file_key}/data/0", data)
    firebase_put(f"cfms/file_list/{file_key}", {
        "filename": "TEST_300K_to_2K.dat",
        "rows": len(data),
        "temp_range": "2.0 - 300.0 K",
        "uploaded_at": meta["uploaded_at"],
    })

    update_status("test_complete", 1)
    print(f"\n  テスト完了! ブラウザで確認してください。")


# ===== メイン =====
def main():
    global running

    print("=" * 60)
    print("  CFMS-5T データ自動送信 (v1.0)")
    print("=" * 60)

    args = sys.argv[1:]

    # テストモード
    if "--test" in args:
        test_mode()
        return

    # 監視フォルダ
    watch_dir = DEFAULT_WATCH_DIR
    for a in args:
        if not a.startswith("--") and os.path.isdir(a):
            watch_dir = a
            break

    if not os.path.exists(watch_dir):
        print(f"\n  [エラー] フォルダが見つかりません: {watch_dir}")
        print(f"  使い方: python cfms_sender.py \"D:\\path\\to\\DATA\"")
        return

    print(f"  監視フォルダ: {watch_dir}")
    print(f"  スキャン間隔: {SCAN_INTERVAL} 秒")
    print(f"  Firebase:     {FIREBASE_URL}")
    print(f"  停止:         Ctrl+C")
    print(f"  Web制御:      cfms-plotter のON/OFFボタン")
    print("=" * 60)

    # 既に送信済みのファイルを Firebase から取得
    known_files = {}
    print("\n  既存ファイル情報を取得中...")
    existing = firebase_get("cfms/file_list")
    if existing:
        print(f"  Firebase に {len(existing)} ファイル登録済み")
        # ハッシュマッチングは初回スキャンで行う
    else:
        print(f"  Firebase にファイルなし（初回スキャン）")

    # 初期ステータス
    update_status("scanning", 0)

    # 初回フルスキャン
    print(f"\n  初回スキャン中: {watch_dir}")
    all_dats = []
    for root, dirs, files in os.walk(watch_dir):
        for fname in files:
            if fname.lower().endswith('.dat'):
                all_dats.append(os.path.join(root, fname))

    print(f"  .dat ファイル: {len(all_dats)} 個検出")

    # 既に送信済みかチェック（ハッシュ比較）
    files_to_send = []
    for fpath in all_dats:
        fhash = get_file_hash(fpath)
        file_key = sanitize_key(os.path.basename(fpath).replace('.dat', ''))

        # Firebase に同じハッシュがあればスキップ
        if existing and file_key in existing:
            known_files[fpath] = fhash
            continue

        files_to_send.append(fpath)
        known_files[fpath] = fhash

    if files_to_send:
        print(f"  新規ファイル: {len(files_to_send)} 個")
        for i, fpath in enumerate(files_to_send):
            if not running:
                break
            if not check_enabled():
                print("  [一時停止] Web から OFF にされました")
                while not check_enabled() and running:
                    time.sleep(5)
                if not running:
                    break
                print("  [再開] ON に戻りました")

            file_key = sanitize_key(os.path.basename(fpath).replace('.dat', ''))
            print(f"\n  [{i+1}/{len(files_to_send)}] 送信中...")
            send_file(fpath, file_key)
            update_status("sending", i + 1)
    else:
        print(f"  全ファイル送信済み")

    update_status("watching", len(known_files))
    print(f"\n  監視モードに移行... (Ctrl+C で停止)\n")

    # 監視ループ
    while running:
        if not check_enabled():
            print("  [一時停止] Web から OFF")
            update_status("paused", len(known_files))
            while not check_enabled() and running:
                time.sleep(5)
            if not running:
                break
            print("  [再開]")
            update_status("watching", len(known_files))

        new_files = scan_folder(watch_dir, known_files)
        if new_files:
            print(f"\n  新しいファイル検出: {len(new_files)} 個")
            for fpath in new_files:
                if not running:
                    break
                file_key = sanitize_key(os.path.basename(fpath).replace('.dat', ''))
                send_file(fpath, file_key)

            update_status("watching", len(known_files))

        time.sleep(SCAN_INTERVAL)

    update_status("stopped", len(known_files))
    print("終了しました。")


if __name__ == "__main__":
    main()
