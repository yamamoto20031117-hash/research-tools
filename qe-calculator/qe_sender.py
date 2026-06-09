#!/usr/bin/env python3
"""
QE 計算結果 自動送信スクリプト（lab-ubuntu / qe-auto → Firebase）

results.html は次の形の JSON を読む:
  - 一覧:   <base>/qe/results.json
            = {"generated_at", "n_results", "results": [ {pk,label,process_label,
              state,finished_ok,formula,natoms,total_energy_ev,fermi_energy_ev,
              band_gap_ev,is_metallic,total_magnetization,ctime}, ... ]}
  - 詳細:   <base>/qe/<endpoint>/<pk>.json   (endpoint = bands|pdos|structure|trajectory|details)

このスクリプトは lab-ubuntu の既存ローカル結果サーバ（Tailscale LIVE と同じ JSON を返す）
または書き出した JSON ディレクトリの内容を、そのまま Firebase RTDB に PUT して
公開ダッシュボード(results.html)から誰でも見られるようにする「中継役」。

使い方:
  # 既存ローカルサーバ（results.json と /<endpoint>/<pk> を返す）を中継
  python3 qe_sender.py --from-url http://localhost:8000
  # 5 秒ごとに継続同期
  python3 qe_sender.py --from-url http://localhost:8000 --watch 5
  # JSON ディレクトリ（results.json + <endpoint>/<pk>.json）を中継
  python3 qe_sender.py --from-dir ./export
  # パイプライン確認用のデモデータを push（計算結果が無くても表示テストできる）
  python3 qe_sender.py --demo
  # qe 名前空間を消す
  python3 qe_sender.py --clear

必要パッケージ: なし（Python 標準ライブラリのみ: urllib, json, argparse, time）
"""

import sys
import json
import time
import argparse
import urllib.request
import urllib.error

# ===== 設定 =====
DEFAULT_FB_URL = "https://research-tools-board-default-rtdb.firebaseio.com"  # 他ツールと共有の board DB
DEFAULT_NS = "qe"
# results.html の ENDPOINT マップと一致させること（url 名）
ENDPOINTS = ["bands", "pdos", "structure", "trajectory", "details"]
# 詳細を持つ WorkChain（results.html の hasDetails と一致）
DETAIL_LABELS = {"QeFullWorkChain", "PwRelaxWorkChain", "PwBandsWorkChain", "PdosWorkChain"}


# ===== Firebase RTDB REST =====
def firebase_put(fb_url, path, data):
    """RTDB の <path> に PUT（その階層をまるごと置換）。成功で True。"""
    url = f"{fb_url}/{path}.json"
    payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url, data=payload, method="PUT",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.status == 200
    except Exception as e:
        print(f"  [Firebase PUT エラー] {path}: {e}")
        return False


def firebase_delete(fb_url, path):
    url = f"{fb_url}/{path}.json"
    req = urllib.request.Request(url, method="DELETE")
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.status == 200
    except Exception as e:
        print(f"  [Firebase DELETE エラー] {path}: {e}")
        return False


# ===== ソース取得（URL / ディレクトリ） =====
def http_get_json(base, rel):
    url = base.rstrip("/") + "/" + rel.lstrip("/")
    with urllib.request.urlopen(url, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))


def read_dir_json(root, rel):
    import os
    path = os.path.join(root, rel)
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ===== 中継本体 =====
def detail_pks(results):
    return [r.get("pk") for r in results if r.get("process_label") in DETAIL_LABELS and r.get("pk") is not None]


def mirror(fb_url, ns, get_results, get_detail):
    """get_results() -> 一覧 dict / get_detail(endpoint, pk) -> 詳細 dict or None を受け、Firebase へ PUT。"""
    listing = get_results()
    if not listing or "results" not in listing:
        print("  [中止] 一覧 (results.json) が取得できませんでした")
        return False
    ok = firebase_put(fb_url, f"{ns}/results", listing)
    n = len(listing.get("results", []))
    print(f"  results → {ns}/results  ({n} 件)  {'OK' if ok else 'NG'}")

    pushed = 0
    for pk in detail_pks(listing["results"]):
        for ep in ENDPOINTS:
            try:
                d = get_detail(ep, pk)
            except Exception:
                d = None
            if d is None:
                continue
            if firebase_put(fb_url, f"{ns}/{ep}/{pk}", d):
                pushed += 1
    print(f"  詳細 → {pushed} エンドポイント push")
    return ok


def run_from_url(fb_url, ns, base):
    return mirror(
        fb_url, ns,
        get_results=lambda: http_get_json(base, "results.json"),
        get_detail=lambda ep, pk: _try(lambda: http_get_json(base, f"{ep}/{pk}")),
    )


def run_from_dir(fb_url, ns, root):
    return mirror(
        fb_url, ns,
        get_results=lambda: read_dir_json(root, "results.json"),
        get_detail=lambda ep, pk: read_dir_json(root, f"{ep}/{pk}.json"),
    )


def _try(fn):
    try:
        return fn()
    except Exception:
        return None


# ===== デモ（計算が無くても表示確認できる最小データ。物性値は捏造せず未定義のまま） =====
def push_demo(fb_url, ns):
    listing = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "n_results": 4,
        "results": [
            {"pk": 9001, "label": "VSe2 (pristine) [DEMO]", "process_label": "QeFullWorkChain",
             "state": "finished", "finished_ok": True, "formula": "VSe2", "natoms": 3,
             "is_metallic": True, "ctime": time.strftime("%Y-%m-%dT%H:%M:%S+00:00")},
            {"pk": 9002, "label": "VSe2 + EMIm+ [DEMO]", "process_label": "QeFullWorkChain",
             "state": "finished", "finished_ok": True, "formula": "C6H11N2·VSe2", "natoms": 22,
             "is_metallic": True, "ctime": time.strftime("%Y-%m-%dT%H:%M:%S+00:00")},
            {"pk": 9003, "label": "VSe2 + DBPO (neutral) [DEMO]", "process_label": "QeFullWorkChain",
             "state": "waiting", "finished_ok": False, "formula": "C40H22N2O2·VSe2", "natoms": 69,
             "ctime": time.strftime("%Y-%m-%dT%H:%M:%S+00:00")},
            {"pk": 9004, "label": "VSe2 + DBPO radical-cation [DEMO]", "process_label": "QeFullWorkChain",
             "state": "created", "finished_ok": False, "formula": "C40H22N2O2(+•)·VSe2", "natoms": 69,
             "ctime": time.strftime("%Y-%m-%dT%H:%M:%S+00:00")},
        ],
    }
    ok = firebase_put(fb_url, f"{ns}/results", listing)
    print(f"  DEMO results → {ns}/results  {'OK' if ok else 'NG'}")
    return ok


def main():
    ap = argparse.ArgumentParser(description="QE 結果を Firebase に送信（results.html 用）")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--from-url", help="ローカル結果サーバの base URL（/results.json と /<endpoint>/<pk> を返す）")
    src.add_argument("--from-dir", help="JSON ディレクトリ（results.json と <endpoint>/<pk>.json）")
    src.add_argument("--demo", action="store_true", help="デモデータを push（表示確認用）")
    src.add_argument("--clear", action="store_true", help="Firebase の qe 名前空間を削除")
    ap.add_argument("--fb-url", default=DEFAULT_FB_URL, help="Firebase RTDB の base URL")
    ap.add_argument("--namespace", default=DEFAULT_NS, help="RTDB 名前空間（既定: qe）")
    ap.add_argument("--watch", type=float, default=0, help="秒間隔で継続同期（0=一回だけ）")
    args = ap.parse_args()

    fb, ns = args.fb_url, args.namespace

    if args.clear:
        print(f"qe 名前空間を削除: {ns}")
        firebase_delete(fb, ns)
        return

    def once():
        print(f"[{time.strftime('%H:%M:%S')}] 同期 → {fb}/{ns}")
        if args.demo:
            return push_demo(fb, ns)
        if args.from_url:
            return run_from_url(fb, ns, args.from_url)
        if args.from_dir:
            return run_from_dir(fb, ns, args.from_dir)

    if args.watch and args.watch > 0:
        print(f"継続同期モード（{args.watch}s 間隔）。Ctrl+C で停止。")
        try:
            while True:
                once()
                time.sleep(args.watch)
        except KeyboardInterrupt:
            print("\n停止しました。")
    else:
        once()


if __name__ == "__main__":
    main()
