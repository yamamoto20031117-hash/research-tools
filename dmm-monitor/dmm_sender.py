#!/usr/bin/env python3
"""
Keithley 2400 SourceMeter リアルタイムモニター — ラボPC用送信スクリプト

使い方:
  1. pip install pyvisa pyvisa-py pyserial
  2. Keithley 2400 を USB or GPIB でラボPCに接続
  3. python dmm_sender.py で実行（まずテストモードで動作確認）
  4. 接続確認後、--live オプションで実機モードに切り替え

コマンド:
  python dmm_sender.py          # テストモード（ダミーデータ）
  python dmm_sender.py --live   # 実機モード（Keithley 2400 に接続）
  python dmm_sender.py --list   # 接続可能なVISAデバイス一覧を表示
"""

import time
import json
import signal
import sys
from datetime import datetime
import urllib.request
import urllib.error

# ===== 設定 =====
FIREBASE_URL = "https://research-tools-board-default-rtdb.firebaseio.com"
FIREBASE_PATH_LIVE = "dmm/live"       # リアルタイム値（最新1件を上書き）
FIREBASE_PATH_LOG = "dmm/log"         # ログ（追記）
INTERVAL = 1.0                         # 測定間隔（秒）

# GPIB接続の場合: "GPIB0::24::INSTR" (アドレス24が一般的)
# USB接続の場合: 自動検出を試みる
DMM_ADDRESS = "GPIB0::24::INSTR"


# ===== Firebase REST API =====
def firebase_put(path, data):
    """Firebase に PUT（上書き）"""
    url = f"{FIREBASE_URL}/{path}.json"
    req = urllib.request.Request(
        url, data=json.dumps(data).encode('utf-8'),
        method='PUT', headers={'Content-Type': 'application/json'}
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status == 200
    except Exception as e:
        print(f"  [Firebase PUT error] {e}")
        return False

def firebase_push(path, data):
    """Firebase に POST（追記）"""
    url = f"{FIREBASE_URL}/{path}.json"
    req = urllib.request.Request(
        url, data=json.dumps(data).encode('utf-8'),
        method='POST', headers={'Content-Type': 'application/json'}
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status == 200
    except Exception as e:
        print(f"  [Firebase POST error] {e}")
        return False


# ===== Keithley 2400 接続・初期化 =====
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
                    print(f"    → {idn}")
                    inst.close()
                except:
                    print(f"    → (IDN取得不可)")
        else:
            print("VISAデバイスが見つかりません")
            print("確認事項:")
            print("  - ケーブルが接続されているか")
            print("  - NI-VISA ドライバがインストールされているか")
            print("  - GPIB-USB アダプタのドライバが入っているか")
    except ImportError:
        print("pyvisa がインストールされていません")
        print("  pip install pyvisa pyvisa-py pyserial")


def connect_keithley():
    """Keithley 2400 に接続"""
    import pyvisa
    rm = pyvisa.ResourceManager()
    resources = rm.list_resources()
    print(f"検出されたVISAリソース: {resources}")

    # 指定アドレスで接続を試みる
    smu = None
    try:
        smu = rm.open_resource(DMM_ADDRESS)
        print(f"  {DMM_ADDRESS} に接続")
    except Exception:
        # 自動検出: Keithley を含むリソースを探す
        print(f"  {DMM_ADDRESS} に接続できません。自動検出中...")
        for r in resources:
            try:
                inst = rm.open_resource(r)
                inst.timeout = 3000
                idn = inst.query("*IDN?").strip()
                if "KEITHLEY" in idn.upper() or "2400" in idn:
                    smu = inst
                    print(f"  Keithley 検出: {r} → {idn}")
                    break
                inst.close()
            except:
                pass

    if not smu:
        print("Keithley 2400 が見つかりません")
        return None

    smu.timeout = 10000
    smu.write_termination = '\n'
    smu.read_termination = '\n'

    # 機器ID
    idn = smu.query("*IDN?").strip()
    print(f"接続成功: {idn}")

    # ===== Keithley 2400 初期設定 =====
    smu.write("*RST")                          # リセット
    time.sleep(0.5)
    smu.write(":SYST:BEEP:STAT OFF")           # ビープ音オフ
    smu.write(":SENS:FUNC:CONC ON")            # 電圧・電流の同時測定ON
    smu.write(":SENS:FUNC 'VOLT:DC','CURR:DC'")# 電圧と電流を測定
    smu.write(":FORM:ELEM VOLT,CURR")          # 読み取りデータに電圧と電流を含める

    # ソース設定（電流源モード・0A出力 = 単純な測定のみ）
    # ※ 既に外部から電流を流している場合はソースをOFFにする
    # smu.write(":SOUR:FUNC CURR")
    # smu.write(":SOUR:CURR 0")
    # smu.write(":OUTP ON")

    print("初期設定完了")
    print("  モード: 電圧・電流 同時測定")
    print("  ※ 出力(OUTPUT)は手動で制御してください")
    return smu


def read_keithley(smu):
    """Keithley 2400 から電圧・電流を読み取る"""
    result = smu.query(":READ?")
    vals = result.strip().split(',')
    voltage = float(vals[0])
    current = float(vals[1])
    return voltage, current


def read_dummy():
    """テスト用ダミーデータ"""
    import random
    voltage = 3.3 + random.gauss(0, 0.01)
    current = 0.015 + random.gauss(0, 0.0005)
    return voltage, current


# ===== メインループ =====
running = True

def signal_handler(sig, frame):
    global running
    print("\n停止中...")
    running = False

signal.signal(signal.SIGINT, signal_handler)


def main():
    mode = "test"
    if "--live" in sys.argv:
        mode = "live"
    if "--list" in sys.argv:
        list_visa_resources()
        return

    print("=" * 56)
    print("  Keithley 2400 リアルタイムモニター")
    print("=" * 56)
    print(f"  モード:     {'実機接続' if mode=='live' else 'テスト（ダミーデータ）'}")
    print(f"  Firebase:   {FIREBASE_URL}")
    print(f"  測定間隔:   {INTERVAL} 秒")
    print(f"  停止:       Ctrl+C")
    print("=" * 56)

    smu = None
    if mode == "live":
        try:
            smu = connect_keithley()
            if not smu:
                print("\n接続失敗。テストモードで続行しますか？ (y/n)")
                if input().strip().lower() != 'y':
                    return
                mode = "test"
        except ImportError:
            print("pyvisa がインストールされていません")
            print("  pip install pyvisa pyvisa-py pyserial")
            return
        except Exception as e:
            print(f"接続エラー: {e}")
            return
    else:
        print("\nテストモードで動作中（ダミーデータを送信）")
        print("実機に接続するには: python dmm_sender.py --live\n")

    count = 0
    errors = 0

    while running:
        try:
            # 測定
            if mode == "live" and smu:
                voltage, current = read_keithley(smu)
            else:
                voltage, current = read_dummy()

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
            power = voltage * current

            # 自動単位
            def fmt_i(i):
                a = abs(i)
                if a < 1e-6: return f"{i*1e9:>8.3f} nA"
                if a < 1e-3: return f"{i*1e6:>8.3f} μA"
                if a < 1:    return f"{i*1e3:>8.4f} mA"
                return f"{i:>8.5f} A"

            def fmt_v(v):
                a = abs(v)
                if a < 1e-3: return f"{v*1e6:>8.2f} μV"
                if a < 1:    return f"{v*1e3:>8.4f} mV"
                return f"{v:>8.5f} V"

            print(f"[{ts}] #{count:>5}  {fmt_v(voltage)}  {fmt_i(current)}  P={power:.6e} W  [{status}]")

            errors = 0  # 成功したらエラーカウントリセット

        except Exception as e:
            errors += 1
            print(f"  [エラー #{errors}] {e}")
            if errors > 10:
                print("  連続エラーが多すぎます。接続を確認してください。")
                if mode == "live" and smu:
                    try:
                        smu.close()
                        print("  再接続中...")
                        smu = connect_keithley()
                        errors = 0
                    except:
                        pass

        time.sleep(INTERVAL)

    # クリーンアップ
    if smu:
        try:
            # smu.write(":OUTP OFF")  # 出力OFF（必要に応じて）
            smu.close()
            print("Keithley 2400 切断完了")
        except:
            pass
    print("終了しました。")


if __name__ == "__main__":
    main()
