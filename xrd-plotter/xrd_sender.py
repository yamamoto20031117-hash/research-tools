#!/usr/bin/env python3
"""
XRD データ自動送信スクリプト（Rigaku SmartLab → Firebase）

使い方:
  python xrd_sender.py --watch "C:/path/to/xrd/output/folder"

指定フォルダに新しい .ras/.raw/.asc/.txt ファイルが保存されたら
自動でパースしてFirebaseに送信 → Webダッシュボードにリアルタイム表示

必要パッケージ:
  pip install watchdog
  (Python 標準ライブラリ: urllib, json, os, sys, time)
"""

import os
import sys
import time
import json
import urllib.request
import urllib.error
import glob

# ===== 設定 =====
FIREBASE_URL = "https://research-tools-board-default-rtdb.firebaseio.com"
FIREBASE_PATH = "xrd/data"
WATCH_EXTENSIONS = {'.ras', '.raw', '.asc', '.txt'}

# ===== Firebase REST API =====
def firebase_push(path, data):
    """Firebase に POST（追記）"""
    url = f"{FIREBASE_URL}/{path}.json"
    payload = json.dumps(data).encode('utf-8')
    req = urllib.request.Request(url, data=payload, method='POST',
                                 headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status == 200
    except Exception as e:
        print(f"  [Firebase送信エラー] {e}")
        return False


# ===== ファイルパーサー =====
def parse_ras(filepath):
    """Rigaku .ras ファイルをパース"""
    x, y = [], []
    in_data = False
    start_angle = 0
    step_angle = 0

    # 複数エンコーディングを試す
    for enc in ['shift_jis', 'utf-8', 'latin-1']:
        try:
            with open(filepath, 'r', encoding=enc) as f:
                lines = f.readlines()
            break
        except (UnicodeDecodeError, UnicodeError):
            continue
    else:
        # バイナリとして読む
        with open(filepath, 'rb') as f:
            raw = f.read()
        lines = raw.decode('latin-1', errors='replace').split('\n')

    for line in lines:
        trimmed = line.strip()
        if trimmed.startswith('*MEAS_SCAN_START '):
            try:
                start_angle = float(trimmed.split()[1])
            except:
                pass
        if trimmed.startswith('*MEAS_SCAN_STEP '):
            try:
                step_angle = float(trimmed.split()[1])
            except:
                pass

        if trimmed == '*RAS_INT_START':
            in_data = True
            continue
        if trimmed == '*RAS_INT_END':
            in_data = False
            continue

        if in_data:
            parts = trimmed.split()
            if len(parts) >= 2:
                try:
                    a, b = float(parts[0]), float(parts[1])
                    if 0 <= a <= 180:
                        x.append(a)
                        y.append(b)
                except ValueError:
                    pass
            elif len(parts) == 1 and step_angle > 0:
                try:
                    b = float(parts[0])
                    angle = start_angle + len(x) * step_angle
                    x.append(angle)
                    y.append(b)
                except ValueError:
                    pass

    return x, y


def parse_generic(filepath):
    """汎用XRDファイル（TXT/ASC/RAW/XY）をパース"""
    x, y = [], []
    for enc in ['shift_jis', 'utf-8', 'latin-1']:
        try:
            with open(filepath, 'r', encoding=enc) as f:
                lines = f.readlines()
            break
        except (UnicodeDecodeError, UnicodeError):
            continue
    else:
        return x, y

    for line in lines:
        trimmed = line.strip()
        if not trimmed or trimmed.startswith('#') or trimmed.startswith('*') or trimmed.startswith(';'):
            continue
        parts = trimmed.replace('\t', ' ').replace(',', ' ').split()
        if len(parts) >= 2:
            try:
                a, b = float(parts[0]), float(parts[1])
                if 0 <= a <= 180:
                    x.append(a)
                    y.append(b)
            except ValueError:
                pass
    return x, y


def parse_file(filepath):
    """ファイル拡張子に応じてパーサーを選択"""
    ext = os.path.splitext(filepath)[1].lower()
    if ext == '.ras':
        return parse_ras(filepath)
    else:
        return parse_generic(filepath)


def send_xrd_data(filepath):
    """XRDデータをFirebaseに送信"""
    name = os.path.basename(filepath)
    print(f"\n  新しいファイルを検出: {name}")

    x, y = parse_file(filepath)
    if len(x) < 5:
        print(f"  データが少なすぎます ({len(x)}点)。スキップ。")
        return False

    print(f"  データ: {len(x)}点, 2θ = {x[0]:.2f}° 〜 {x[-1]:.2f}°")

    data = {
        'name': os.path.splitext(name)[0],
        'x': x,
        'y': y,
        'time': int(time.time() * 1000),
        'points': len(x)
    }

    if firebase_push(FIREBASE_PATH, data):
        print(f"  Firebase送信完了 ✓")
        return True
    else:
        print(f"  Firebase送信失敗 ×")
        return False


# ===== ファイル監視（watchdogなしでも動くポーリング版） =====
def watch_folder(folder):
    """フォルダを監視して新しいXRDファイルを自動送信"""
    print(f"\n{'='*50}")
    print(f"  XRD データ自動送信スクリプト")
    print(f"{'='*50}")
    print(f"  監視フォルダ: {folder}")
    print(f"  対応形式: {', '.join(sorted(WATCH_EXTENSIONS))}")
    print(f"  送信先: Firebase → Webダッシュボード")
    print(f"\n  新しいファイルが保存されると自動で送信されます")
    print(f"  Ctrl+C で停止\n")

    # 既存ファイルを記録（初回起動時に全送信しない）
    known_files = set()
    for ext in WATCH_EXTENSIONS:
        for f in glob.glob(os.path.join(folder, f'*{ext}')):
            known_files.add(f)
        for f in glob.glob(os.path.join(folder, f'*{ext.upper()}')):
            known_files.add(f)

    print(f"  既存ファイル: {len(known_files)}件（スキップ）\n")

    while True:
        try:
            current_files = set()
            for ext in WATCH_EXTENSIONS:
                for f in glob.glob(os.path.join(folder, f'*{ext}')):
                    current_files.add(f)
                for f in glob.glob(os.path.join(folder, f'*{ext.upper()}')):
                    current_files.add(f)

            new_files = current_files - known_files
            for filepath in sorted(new_files):
                # ファイルの書き込みが完了するまで少し待つ
                time.sleep(2)
                try:
                    send_xrd_data(filepath)
                except Exception as e:
                    print(f"  [エラー] {filepath}: {e}")
                known_files.add(filepath)

            time.sleep(3)  # 3秒ごとにチェック

        except KeyboardInterrupt:
            print("\n\n  停止しました。")
            break
        except Exception as e:
            print(f"  [監視エラー] {e}")
            time.sleep(5)


# ===== 手動送信モード =====
def send_single(filepath):
    """単一ファイルを手動送信"""
    if not os.path.exists(filepath):
        print(f"ファイルが見つかりません: {filepath}")
        return
    send_xrd_data(filepath)


# ===== メイン =====
if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("使い方:")
        print("  フォルダ監視:  python xrd_sender.py --watch <フォルダパス>")
        print("  手動送信:      python xrd_sender.py <ファイルパス>")
        print()
        print("例:")
        print('  python xrd_sender.py --watch "C:\\SmartLab\\Data"')
        print('  python xrd_sender.py measurement.ras')
        sys.exit(1)

    if sys.argv[1] == '--watch':
        folder = sys.argv[2] if len(sys.argv) > 2 else '.'
        if not os.path.isdir(folder):
            print(f"フォルダが見つかりません: {folder}")
            sys.exit(1)
        watch_folder(folder)
    else:
        send_single(sys.argv[1])
