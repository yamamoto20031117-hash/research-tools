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
DMM_ADDRESS = "ASRL/dev/cu.usbserial-AO006ZV3::INSTR"


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


def firebase_get(path):
    """Firebase から GET"""
    url = f"{FIREBASE_URL}/{path}.json"
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            return json.loads(resp.read().decode('utf-8'))
    except:
        return None

def firebase_delete(path):
    """Firebase から DELETE"""
    url = f"{FIREBASE_URL}/{path}.json"
    req = urllib.request.Request(url, method='DELETE')
    try:
        urllib.request.urlopen(req, timeout=5)
    except:
        pass

def update_output_status(on):
    """OUTPUT状態をFirebaseに送信（ダッシュボードで監視）"""
    firebase_put("dmm/status", {"output": on, "time": int(time.time()*1000)})


def flush_buffer(smu):
    """RS-232入力バッファをクリア"""
    if not smu:
        return
    try:
        if smu.bytes_in_buffer > 0:
            smu.read_bytes(smu.bytes_in_buffer)
    except:
        pass


def safe_write(smu, cmd, delay=0.5):
    """エラークリア + バッファクリア付きで安全にSCPIコマンドを送信"""
    if not smu:
        return
    flush_buffer(smu)
    try:
        smu.write(cmd)
    except Exception as e:
        print(f"  [SCPI write error] {cmd} → {e}")
        # エラー後にクリアして再試行
        time.sleep(0.5)
        flush_buffer(smu)
        try:
            smu.write("*CLS")
            time.sleep(0.3)
            smu.write(cmd)
        except Exception as e2:
            print(f"  [SCPI retry failed] {cmd} → {e2}")
    time.sleep(delay)


# ===== タイマー自動停止 =====
auto_stop_time = 0  # 0 = 無制限


def check_auto_stop(smu):
    """タイマー自動停止をチェック"""
    global auto_stop_time
    if auto_stop_time > 0 and time.time() >= auto_stop_time:
        print("\n  *** タイマー満了: OUTPUT OFF (自動停止) ***")
        safe_write(smu, "*CLS", 0.3)
        safe_write(smu, ":OUTP OFF", 0.5)
        auto_stop_time = 0
        update_output_status(False)
        return True
    return False


def configure_source(smu, mode, value, compliance):
    """ソースモードと値を設定（RS-232安全版）"""
    if not smu:
        print(f"  [テストモード] SOURCE設定: {mode} = {value}, Compliance = {compliance}")
        return

    # まずOUTPUT OFFにしてから設定変更（安全のため）
    safe_write(smu, ":OUTP OFF", 0.5)
    # エラーキュークリア
    safe_write(smu, "*CLS", 0.5)

    # ソースモード設定
    if mode == "CURR":
        safe_write(smu, ":SOUR:FUNC CURR", 0.5)
        # レンジ：0の場合はMINレンジ
        if abs(value) > 0:
            safe_write(smu, f":SOUR:CURR:RANG {abs(value)}", 0.5)
        else:
            safe_write(smu, ":SOUR:CURR:RANG MIN", 0.5)
        safe_write(smu, f":SOUR:CURR {value}", 0.5)
        # コンプライアンス（電圧上限）
        safe_write(smu, f":SENS:VOLT:PROT {compliance}", 0.5)
        print(f"  設定: 定電流モード {value} A, コンプライアンス {compliance} V")
    elif mode == "VOLT":
        safe_write(smu, ":SOUR:FUNC VOLT", 0.5)
        if abs(value) > 0:
            safe_write(smu, f":SOUR:VOLT:RANG {abs(value)}", 0.5)
        else:
            safe_write(smu, ":SOUR:VOLT:RANG MIN", 0.5)
        safe_write(smu, f":SOUR:VOLT {value}", 0.5)
        # コンプライアンス（電流上限）
        safe_write(smu, f":SENS:CURR:PROT {compliance}", 0.5)
        print(f"  設定: 定電圧モード {value} V, コンプライアンス {compliance} A")

    # 測定関数は常に電圧・電流同時
    safe_write(smu, ":SENS:FUNC:CONC ON", 0.5)
    safe_write(smu, ":SENS:FUNC 'VOLT:DC','CURR:DC'", 0.5)
    safe_write(smu, ":FORM:ELEM VOLT,CURR", 0.5)


def check_command(smu):
    """Firebaseからコマンドを取得して実行"""
    global auto_stop_time
    cmd = firebase_get("dmm/command")
    if not cmd or not cmd.get("action"):
        return None

    action = cmd["action"]
    firebase_delete("dmm/command")  # コマンド消費

    if action == "OUTPUT_OFF":
        print("\n  *** Web からの指令: OUTPUT OFF ***")
        safe_write(smu, "*CLS", 0.3)
        safe_write(smu, ":OUTP OFF", 0.5)
        auto_stop_time = 0
        update_output_status(False)
        return "OFF"

    elif action == "OUTPUT_ON":
        print("\n  *** Web からの指令: OUTPUT ON ***")
        safe_write(smu, "*CLS", 0.3)
        safe_write(smu, ":OUTP ON", 1.0)
        # 確認
        if smu:
            try:
                flush_buffer(smu)
                state = smu.query(":OUTP?").strip()
                print(f"  OUTPUT 状態確認: {state}")
                if state not in ("1", "ON"):
                    print("  OUTPUT ON に失敗。リトライ...")
                    safe_write(smu, "*CLS", 0.5)
                    safe_write(smu, ":OUTP ON", 1.0)
            except Exception as e:
                print(f"  OUTPUT 確認エラー: {e}")
        update_output_status(True)
        return "ON"

    elif action == "SOURCE_START":
        mode = cmd.get("mode", "CURR")       # "CURR" or "VOLT"
        value = float(cmd.get("value", 0))    # 実値（A or V）
        compliance = float(cmd.get("compliance", 21))
        duration = float(cmd.get("duration", 0))  # 秒（0=無制限）

        mode_label = "定電流" if mode == "CURR" else "定電圧"
        unit = "A" if mode == "CURR" else "V"
        print(f"\n  *** Web からの指令: SOURCE START ***")
        print(f"  モード: {mode_label} ({mode})")
        print(f"  ソース値: {value} {unit}")
        print(f"  コンプライアンス: {compliance}")
        if duration > 0:
            print(f"  出力時間: {duration} 秒（自動停止あり）")
        else:
            print(f"  出力時間: 無制限")

        # ソース設定（内部でOUTPUT OFF → 設定変更）
        configure_source(smu, mode, value, compliance)

        # OUTPUT ON（確認付き）
        safe_write(smu, ":OUTP ON", 1.0)

        # OUTPUT状態を確認
        if smu:
            try:
                flush_buffer(smu)
                state = smu.query(":OUTP?").strip()
                print(f"  OUTPUT 状態確認: {state}")
                if state not in ("1", "ON"):
                    print("  OUTPUT ON に失敗。リトライ...")
                    safe_write(smu, "*CLS", 0.5)
                    safe_write(smu, ":OUTP ON", 1.0)
                    state = smu.query(":OUTP?").strip()
                    print(f"  OUTPUT 状態確認（リトライ後）: {state}")
            except Exception as e:
                print(f"  OUTPUT 確認エラー: {e}")

        update_output_status(True)

        # タイマー設定
        if duration > 0:
            auto_stop_time = time.time() + duration
            print(f"  自動停止予定: {datetime.fromtimestamp(auto_stop_time).strftime('%H:%M:%S')}")
        else:
            auto_stop_time = 0

        return "ON"

    return None


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

    smu.timeout = 30000  # RS-232は遅いので30秒に
    smu.write_termination = '\r'   # Keithley 2400 RS-232はCR終端
    smu.read_termination = '\r'
    # RS-232設定（Keithley 2400のデフォルト: 9600baud, 8bit, 1stop, no parity）
    smu.baud_rate = 9600
    smu.data_bits = 8
    smu.stop_bits = pyvisa.constants.StopBits.one
    smu.parity = pyvisa.constants.Parity.none
    smu.flow_control = pyvisa.constants.VI_ASRL_FLOW_NONE

    # 入力バッファクリア
    try:
        smu.read_bytes(smu.bytes_in_buffer) if smu.bytes_in_buffer > 0 else None
    except:
        pass

    # 機器ID
    idn = smu.query("*IDN?").strip()
    print(f"接続成功: {idn}")

    # ===== Keithley 2400 初期設定 =====
    print("初期設定中...")
    safe_write(smu, "*RST", 2.0)  # RST後は2秒待つ
    safe_write(smu, "*CLS", 0.5)  # エラーキュークリア

    safe_write(smu, ":SYST:BEEP:STAT OFF", 0.5)
    safe_write(smu, ":SENS:FUNC:CONC ON", 0.5)
    safe_write(smu, ":SENS:FUNC 'VOLT:DC','CURR:DC'", 0.5)
    safe_write(smu, ":FORM:ELEM VOLT,CURR", 0.5)

    # ソース設定（電流源モード・0A — OUTPUT はOFFのまま待機）
    safe_write(smu, ":SOUR:FUNC CURR", 0.5)
    safe_write(smu, ":SOUR:CURR:RANG MIN", 0.5)
    safe_write(smu, ":SOUR:CURR 0", 0.5)
    # OUTPUT OFF のまま（Webダッシュボードからの指令で ON にする）

    print("初期設定完了")
    print("  モード: 電圧・電流 同時測定")
    print("  ソース: 0A（待機中）")
    print("  OUTPUT: OFF（Webから制御）")
    update_output_status(False)
    return smu


def read_keithley(smu):
    """Keithley 2400 から電圧・電流を読み取る"""
    flush_buffer(smu)
    # :READ? がタイムアウトする場合は :MEAS? を試す
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
    output_on = False  # OUTPUT状態トラッキング（起動時はOFF）

    # 自動単位フォーマット関数
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

    print("\n  OUTPUT OFF — Webダッシュボードからの指令を待機中...")

    while running:
        try:
            # Webダッシュボードからのコマンドをチェック
            cmd_result = check_command(smu)
            if cmd_result == "OFF":
                output_on = False
                print("\n  OUTPUT OFF — 測定停止。コマンド待機中...")
            elif cmd_result == "ON":
                output_on = True
                print("\n  OUTPUT ON — 測定開始")

            # タイマー自動停止チェック
            if check_auto_stop(smu):
                output_on = False
                print("\n  OUTPUT OFF（タイマー満了）— コマンド待機中...")

            # OUTPUT OFF の間は測定スキップ（:READ? がハングするのを防ぐ）
            if not output_on:
                time.sleep(INTERVAL)
                continue

            # 測定（OUTPUT ON 時のみ）
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

            # タイマー残り表示
            timer_str = ""
            if auto_stop_time > 0:
                remain = max(0, int(auto_stop_time - time.time()))
                m, s = divmod(remain, 60)
                timer_str = f"  ⏱{m:02d}:{s:02d}"

            print(f"[{ts}] #{count:>5}  {fmt_v(voltage)}  {fmt_i(current)}{timer_str}  [{status}]")

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
            smu.write(":OUTP OFF")  # 出力OFF
            smu.close()
            print("Keithley 2400 切断完了")
        except:
            pass
    print("終了しました。")


if __name__ == "__main__":
    main()
