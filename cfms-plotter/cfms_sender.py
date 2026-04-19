#!/usr/bin/env python3
"""
CFMS-5T データ自動送信スクリプト v3.0

使い方:
  python cfms_sender.py              # 自動送信 → 監視モード
  python cfms_sender.py --test       # テストモード

起動すると:
  1. 指定フォルダの既存 .dat ファイルを全て送信
  2. 送信後、自動で新規ファイル監視モードに移行
  3. 対象フォルダ: inaba, Mizuguchi, Okuda, Yamamoto, Yamashita, Yokoi
"""

import time
import json
import signal
import sys
import os
from datetime import datetime
import urllib.request
import urllib.error

# ===== 設定 =====
FIREBASE_URL = "https://research-tools-board-default-rtdb.firebaseio.com"
DEFAULT_WATCH_DIR = r"C:\Users\User\Desktop\DATA"
SCAN_INTERVAL = 10
MAX_ROWS_PER_FILE = 20000

# 対象フォルダ（アクティブユーザーのみ）
ACTIVE_FOLDERS = [
    "inaba",
    "Mizuguchi",
    "Okuda",
    "Yamamoto",
    "Yamashita",
    "Yokoi",
]

KEY_COLUMNS = [
    "Time", "R_nv", "R_s", "sensor_B_(K)", "T_VTI_(K)",
    "B_digital_(T)", "I_s", "V_s", "V_nv"
]

running = True


# ===== Firebase REST API =====
def firebase_put(path, data, timeout=30, retries=3):
    url = f"{FIREBASE_URL}/{path}.json"
    payload = json.dumps(data).encode('utf-8')
    for attempt in range(retries):
        req = urllib.request.Request(
            url, data=payload,
            method='PUT', headers={'Content-Type': 'application/json'}
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.status == 200
        except Exception as e:
            print(f"  [Firebase PUT error] attempt {attempt+1}/{retries}: {e}")
            if attempt < retries - 1:
                time.sleep(2 * (attempt + 1))
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
    try:
        stat = os.stat(filepath)
        return f"{stat.st_size}_{int(stat.st_mtime)}"
    except:
        return None


def sanitize_key(name):
    for ch in '.#$[]/ \\':
        name = name.replace(ch, '_')
    return name


# ===== ファイル送信 =====
def send_file(filepath, file_key, folder_name=""):
    basename = os.path.basename(filepath)

    print(f"\n  --- {basename} ---")
    print(f"  パース中...")

    headers, data = parse_dat_file(filepath)
    if not data:
        print(f"  [スキップ] データなし: {basename}")
        return False

    print(f"  {len(data):,} 行パース完了")

    chunk_size = 2000
    total_chunks = (len(data) + chunk_size - 1) // chunk_size

    # ファイル作成日時を取得
    try:
        file_ctime = int(os.path.getctime(filepath) * 1000)
        file_mtime = int(os.path.getmtime(filepath) * 1000)
    except:
        file_ctime = int(time.time() * 1000)
        file_mtime = file_ctime

    meta = {
        "filename": basename,
        "folder": folder_name,
        "path": filepath,
        "columns": headers,
        "key_columns": KEY_COLUMNS,
        "total_rows": len(data),
        "chunks": total_chunks,
        "uploaded_at": int(time.time() * 1000),
        "file_created": file_ctime,
        "file_modified": file_mtime,
        "file_hash": get_file_hash(filepath),
    }

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

    for i in range(total_chunks):
        chunk = data[i * chunk_size : (i + 1) * chunk_size]
        print(f"  チャンク {i+1}/{total_chunks} 送信中 ({len(chunk)} 行)...")
        ok = firebase_put(f"cfms/files/{file_key}/data/{i}", chunk, timeout=60)
        if not ok:
            print(f"  [エラー] チャンク {i+1} 送信失敗")
            return False

    firebase_put(f"cfms/file_list/{file_key}", {
        "filename": basename,
        "folder": folder_name,
        "rows": len(data),
        "temp_range": f"{meta.get('temp_min','?')} - {meta.get('temp_max','?')} K",
        "uploaded_at": meta["uploaded_at"],
        "file_created": file_ctime,
        "file_modified": file_mtime,
    })

    print(f"  完了! {len(data):,} 行送信")
    return True


# ===== フォルダスキャン（対象フォルダのみ） =====
def get_active_folders(watch_dir):
    """対象フォルダの .dat ファイル一覧を取得（大文字小文字を柔軟にマッチ）"""
    result = {}  # {実際のフォルダ名: [.dat ファイルリスト]}

    # 実際のフォルダ名を取得して ACTIVE_FOLDERS とマッチ
    try:
        entries = os.listdir(watch_dir)
    except Exception as e:
        print(f"  [エラー] フォルダ読み取り失敗: {e}")
        return result

    active_lower = [f.lower() for f in ACTIVE_FOLDERS]

    for entry in entries:
        entry_path = os.path.join(watch_dir, entry)
        if not os.path.isdir(entry_path):
            continue
        if entry.lower() in active_lower:
            # このフォルダ以下の .dat ファイルを再帰的に探す
            dat_files = []
            for root, dirs, files in os.walk(entry_path):
                for fname in files:
                    if fname.lower().endswith('.dat'):
                        dat_files.append(os.path.join(root, fname))
            result[entry] = dat_files

    return result


def scan_active_folders(watch_dir, known_files):
    """対象フォルダのみスキャンして新規・更新ファイルを検出"""
    new_files = []
    folders = get_active_folders(watch_dir)
    # watch_dir をクロージャで参照

    for folder_name, dat_paths in folders.items():
        for fpath in dat_paths:
            fhash = get_file_hash(fpath)
            if fhash and known_files.get(fpath) != fhash:
                rel_dir = os.path.relpath(os.path.dirname(fpath), watch_dir).replace('\\', '/')
                new_files.append((fpath, rel_dir))
                known_files[fpath] = fhash

    return new_files


# ===== コントロール =====
def check_enabled():
    try:
        ctrl = firebase_get("cfms/control")
        if ctrl and ctrl.get("enabled") == False:
            return False
    except:
        pass
    return True


def update_status(status_text, file_count=0):
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
    import random

    print("\n  テストモード: ダミーデータを Firebase に送信\n")

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
    print("  CFMS-5T データ送信ツール (v3.0)")
    print("  対象フォルダ自動送信 + 監視モード")
    print("=" * 60)

    args = sys.argv[1:]

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
        print(f'  使い方: python cfms_sender.py "D:\\path\\to\\DATA"')
        return

    print(f"  監視フォルダ: {watch_dir}")
    print(f"  Firebase:     {FIREBASE_URL}")
    print(f"  停止:         Ctrl+C")
    print(f"\n  対象フォルダ:")
    for f in ACTIVE_FOLDERS:
        print(f"    - {f}")

    # 対象フォルダの既存ファイルを取得
    folders = get_active_folders(watch_dir)
    known_files = {}
    sent_count = 0

    if not folders:
        print(f"\n  [警告] 対象フォルダに .dat ファイルが見つかりません")
    else:
        # 存在するフォルダを表示
        total_files = sum(len(files) for files in folders.values())
        print(f"\n{'='*60}")
        print(f"  既存ファイル送信開始")
        print(f"  フォルダ数: {len(folders)} / ファイル数: {total_files}")
        print(f"{'='*60}")

        for folder_name in sorted(folders.keys()):
            if not running:
                break

            dat_paths = folders[folder_name]
            print(f"\n  ========================================")
            print(f"  フォルダ: {folder_name}")
            print(f"  ファイル数: {len(dat_paths)}")
            print(f"  ========================================")

            for fpath in dat_paths:
                if not running:
                    break
                basename = os.path.basename(fpath)
                # サブフォルダの相対パスを取得 (例: Okuda/TiSe2 MBA)
                rel_dir = os.path.relpath(os.path.dirname(fpath), watch_dir).replace('\\', '/')
                file_key = sanitize_key(f"{rel_dir}__{basename.replace('.dat', '')}")
                send_file(fpath, file_key, rel_dir)
                known_files[fpath] = get_file_hash(fpath)
                sent_count += 1

        print(f"\n  既存ファイル送信完了! {sent_count} ファイル送信しました。")

    # 監視モードへ移行
    update_status("watching", sent_count)
    print(f"\n{'='*60}")
    print(f"  監視モードに移行")
    print(f"  対象フォルダに新しい .dat ファイルが追加されたら自動送信")
    print(f"  停止: Ctrl+C")
    print(f"{'='*60}\n")

    while running:
        if not check_enabled():
            print("  [一時停止] Web から OFF")
            update_status("paused", sent_count)
            while not check_enabled() and running:
                time.sleep(5)
            if not running:
                break
            print("  [再開]")
            update_status("watching", sent_count)

        new_files = scan_active_folders(watch_dir, known_files)
        if new_files:
            print(f"\n  新しいファイル検出: {len(new_files)} 個")
            for fpath, folder_name in new_files:
                if not running:
                    break
                basename = os.path.basename(fpath)
                file_key = sanitize_key(f"{folder_name}__{basename.replace('.dat', '')}")
                send_file(fpath, file_key, folder_name)
                sent_count += 1

            update_status("watching", sent_count)

        time.sleep(SCAN_INTERVAL)

    update_status("stopped", sent_count)
    print("終了しました。")


if __name__ == "__main__":
    main()
