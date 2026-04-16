#!/usr/bin/env python3
"""
DMM リアルタイムモニター — ラボPC用送信スクリプト

使い方:
  1. pip install pyvisa pyserial firebase-admin (必要に応じて pyvisa-py も)
  2. このスクリプトの DMM_ADDRESS を自分の機器に合わせて変更
  3. Firebase の認証情報（サービスアカウントJSON）を設定
  4. python dmm_sender.py で実行

対応機器（型番確認後にコメントを外す）:
  - Keysight 344xxA シリーズ
  - Keithley 2000/2100/2400 シリーズ
  - HIOKI DT4281/4282 シリーズ
  - Rigaku対応機器
  - その他 SCPI 準拠の DMM
"""

import time
import json
import signal
import sys
from datetime import datetime

# ===== 設定 =====
FIREBASE_URL = "https://research-tools-board-default-rtdb.firebaseio.com"
FIREBASE_PATH_LIVE = "dmm/live"       # リアルタイム値（最新1件を上書き）
FIREBASE_PATH_LOG = "dmm/log"         # ログ（追記）
INTERVAL = 1.0                         # 測定間隔（秒）
DMM_ADDRESS = "USB0::0x0000::0x0000::SERIAL::INSTR"  # 後で変更

# Firebase認証なし（Realtime Database のルールが公開の場合）
# 研究室内のみで使うなら認証なしでOK。セキュリティが必要なら firebase-admin を使う。
USE_REST_API = True  # REST API（認証不要版）を使用

# ===== Firebase REST API（認証不要版） =====
import urllib.request
import urllib.error

def firebase_put(path, data):
    """Firebase Realtime Database に PUT（上書き）"""
    url = f"{FIREBASE_URL}/{path}.json"
    req = urllib.request.Request(
        url,
        data=json.dumps(data).encode('utf-8'),
        method='PUT',
        headers={'Content-Type': 'application/json'}
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status == 200
    except Exception as e:
        print(f"  [Firebase PUT error] {e}")
        return False

def firebase_push(path, data):
    """Firebase Realtime Database に POST（追記）"""
    url = f"{FIREBASE_URL}/{path}.json"
    req = urllib.request.Request(
        url,
        data=json.dumps(data).encode('utf-8'),
        method='POST',
        headers={'Content-Type': 'application/json'}
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status == 200
    except Exception as e:
        print(f"  [Firebase POST error] {e}")
        return False


# ===== DMM 接続 =====
def connect_dmm_visa():
    """VISA経由でDMMに接続（pyvisa使用）"""
    try:
        import pyvisa
        rm = pyvisa.ResourceManager()

        # 接続可能なデバイス一覧を表示
        resources = rm.list_resources()
        print(f"検出されたVISAリソース: {resources}")

        if not resources:
            print("VISAデバイスが見つかりません")
            return None

        # DMM_ADDRESS で接続。見つからない場合は最初のリソースを試す
        try:
            dmm = rm.open_resource(DMM_ADDRESS)
        except Exception:
            print(f"  {DMM_ADDRESS} に接続できません。最初のリソースを試します...")
            dmm = rm.open_resource(resources[0])

        dmm.timeout = 5000  # 5秒タイムアウト

        # 機器ID取得
        try:
            idn = dmm.query("*IDN?").strip()
            print(f"接続成功: {idn}")
        except Exception:
            print("接続成功（IDN取得不可）")

        return dmm
    except ImportError:
        print("pyvisa がインストールされていません: pip install pyvisa pyvisa-py")
        return None
    except Exception as e:
        print(f"DMM接続エラー: {e}")
        return None


def read_dmm(dmm):
    """DMMから電圧・電流を読み取る（機器に合わせてカスタマイズ）"""
    voltage = 0.0
    current = 0.0

    try:
        # ===== Keysight / Agilent 344xxA =====
        # dmm.write("CONF:VOLT:DC")
        # voltage = float(dmm.query("READ?"))
        # dmm.write("CONF:CURR:DC")
        # current = float(dmm.query("READ?"))

        # ===== Keithley 2400 ソースメータ =====
        # 電圧と電流を同時に読める
        # result = dmm.query(":READ?")
        # vals = result.strip().split(',')
        # voltage = float(vals[0])
        # current = float(vals[1])

        # ===== Keithley 2000/2100 マルチメータ =====
        # dmm.write(":FUNC 'VOLT:DC'")
        # voltage = float(dmm.query(":READ?"))
        # dmm.write(":FUNC 'CURR:DC'")
        # current = float(dmm.query(":READ?"))

        # ===== 汎用 SCPI =====
        # voltage = float(dmm.query("MEAS:VOLT:DC?"))
        # current = float(dmm.query("MEAS:CURR:DC?"))

        # ===== テスト用（ダミーデータ） =====
        import random
        voltage = 3.3 + random.gauss(0, 0.01)
        current = 0.015 + random.gauss(0, 0.0005)

    except Exception as e:
        print(f"  [読み取りエラー] {e}")

    return voltage, current


# ===== メインループ =====
running = True

def signal_handler(sig, frame):
    global running
    print("\n停止中...")
    running = False

signal.signal(signal.SIGINT, signal_handler)


def main():
    print("=" * 50)
    print("DMM リアルタイムモニター 送信スクリプト")
    print("=" * 50)
    print(f"Firebase URL: {FIREBASE_URL}")
    print(f"測定間隔: {INTERVAL} 秒")
    print(f"Ctrl+C で停止")
    print("=" * 50)

    # DMM接続（テスト用はNoneでも動く）
    dmm = connect_dmm_visa()

    count = 0
    while running:
        try:
            # 測定
            voltage, current = read_dmm(dmm)
            now = int(time.time() * 1000)  # ミリ秒タイムスタンプ

            data = {
                "time": now,
                "voltage": round(voltage, 8),
                "current": round(current, 8),
            }

            # Firebase送信
            ok1 = firebase_put(FIREBASE_PATH_LIVE, data)
            ok2 = firebase_push(FIREBASE_PATH_LOG, data)

            count += 1
            ts = datetime.now().strftime("%H:%M:%S")
            status = "OK" if (ok1 and ok2) else "WARN"
            print(f"[{ts}] #{count:>5}  V={voltage:>10.6f} V  I={current:>12.8f} A  P={voltage*current:>12.8f} W  [{status}]")

        except Exception as e:
            print(f"  [エラー] {e}")

        time.sleep(INTERVAL)

    # クリーンアップ
    if dmm:
        try:
            dmm.close()
        except:
            pass
    print("終了しました。")


if __name__ == "__main__":
    main()
