# research-tools（研究ツール集）

研究室向けの計測・解析・可視化ツールを集めた**静的 Web サイト**。各ツールは独立した
1 枚の `index.html`（ビルド工程なし）。Vercel にデプロイされている。

- 本番 URL: https://research-tools-theta.vercel.app/
- リポジトリ: https://github.com/yamamoto20031117-hash/research-tools （`main`）
- 想定ユーザー: 研究室メンバー（分子スピントロニクス / TMD・VSe2 系の物性測定）

## ディレクトリ構成と各ツールの状態

| パス | ツール | 状態 |
|------|--------|------|
| `index.html` | ランディングページ（ツール一覧 + スレッド板） | 公開 |
| `tmd-viewer/` | TMD 結晶構造ビューア（1T / 2H / 1T' / 3R + インターカレーション） | 公開 |
| `spin-texture/` | 磁気テクスチャ 3D ビューア（スキルミオン・DMI・SkX / スライド素材書き出し） | 公開 |
| `chirality-ciss/` | キラリティ・CISS 3D ビューア（鏡像対・CISS・DMI転写 / スライド素材書き出し） | 公開 |
| `xrd-plotter/` | XRD データプロッター（(00l) 系列インデクシング付き） | 公開 |
| `ccm-calculator/` | 連続キラリティ尺度 CCM（Pyodide + OpenChemLib、ブラウザ内完結） | 公開 |
| `dmm-monitor/` | DMM リアルタイム電流・電圧モニター（Keithley 2400） | 作成中 |
| `dmm-monitor-2/` | DMM モニター 2（dmm-monitor の派生版） | 作成中 |
| `dmm-viewer/` | DMM データビューア（測定データ解析） | 作成中 |
| `squid-plotter/` | SQUID 磁化データプロッター | 作成中 |
| `cfms-plotter/` | CFMS 低温物性データプロッター | 作成中 |
| `qe-calculator/` | QE 計算ランチャー（旧 AiiDA REST 投入版は凍結 — 下記参照） | 凍結 |
| `Temudraw/` | 化学構造エディタ | 作成中 |
| `showcase/` | ショーケースページ | 公開 |

各ツールフォルダには `index.html`（本体）と、ものによって `manual.html`（使い方）、
データ送信用の Python スクリプト（`*_sender.py`）が入っている。

## qe-calculator の現状（重要）

このディレクトリのブラウザ実装（CIF → AiiDAlab REST API へ relax/SCF/NSCF/bands を
投入）は **凍結**。原因：標準の AiiDA REST API は基本**読み取り専用**で、ワーク
フローの「投入」ができない（aiida-restapi 別パッケージでも限定的）ため、根本的に
動かない設計だった。

**QE 自動化の本実装は別プロジェクト `~/Projects/qe-auto/` に移管済**（AiiDA 本格採用、
構造アセンブリ＋入力生成＋収束テスト＋ワークフロー＋電荷移動解析の 7 フェーズ Python
パッケージ）。詳細は `~/Projects/qe-auto/docs/PLAN.md`。

`qe-calculator/` ディレクトリ自体は**残す**。将来 `qe-auto` の Phase 5 完了後に、
AiiDA REST API を**読み取り専用**で叩く「結果データベース横断ビュー」（host × molecule
マトリクス、各セル：エネルギー / バンド / DOS / Δρ サマリ）に転用する想定。REST は
読み取りは得意なので、既存 UI 資産（カード／スレッド板等）は活かせる。

## 技術スタック

- 素の HTML / CSS / JavaScript。フレームワーク・ビルドツールなし
- 3D 表示は Three.js（CDN: jsdelivr 読み込み）
- 各ツールに「スレッド板」（コメント掲示板）機能。**Firebase** があれば全ユーザー共有、
  なければブラウザ `localStorage` のローカルモードにフォールバック
- DMM Monitor はリアルタイム同期に Firebase + WebSocket（`sync-server`）を使用

## 開発ワークフロー

ビルド不要。編集 → ブラウザで確認 → commit → push（Vercel が自動デプロイ）。

```bash
# ローカルで開く（任意のツールのフォルダで）
python3 -m http.server 4190   # → http://localhost:4190
# CDN（Three.js / Firebase）を使うためネット接続が必要
```

`vercel.json` で `/tmd-viewer` などの拡張子なし URL を `index.html` にリライトしている。
ツールを追加・改名したらここも更新すること。

## 環境変数 / Firebase

- `.env.local` は `.gitignore` 済み。中身は Vercel が自動生成する `VERCEL_OIDC_TOKEN` のみで、
  アプリの動作には不要（手動設定するシークレットは無い）
- Firebase の設定値は各 HTML / Python 内に直書きされている
- Firebase 未設定でもスレッド板はローカルモードで動く

## DMM Monitor まわり（ラボ PC 運用）

`dmm-monitor/` はラボの Windows PC で動かす計測ツール。詳細は
[`dmm-monitor/LAB_PC_SETUP.md`](dmm-monitor/LAB_PC_SETUP.md) を参照。

- `dmm_sender.py` — Keithley 2400 からシリアルで測定値を読み、WebSocket / Firebase へ送信
- `sync-server/` — 端末間でグラフを共有する Node.js WebSocket サーバ（ポート 8765）
- `start_all.bat` — ラボ PC で sync-server + sender をまとめて起動
- Mac でコード修正 → push、ラボ PC は `git pull` → `start_all.bat` 再起動

## 現在の状態・次にやること

> このセクションは引き継ぎ時に手で更新すること。

- 2026-08-05: **スライド素材ジェネレータ 2 本を追加**（`spin-texture/`, `chirality-ciss/`）。
  PowerPoint/Keynote 用の**背景透過 PNG / 4K / 回転連番**を書き出せる。論文用（白背景）と
  発表用（暗背景）の配色切替つき。構想と素材カタログは `PLAN-3d-slide-assets.md`。
  - `spin-texture/` — スキルミオン(Bloch/Néel)・反スキルミオン・メロン・SkX格子・らせん・
    磁壁・DMIのねじれ。**トポロジカル電荷 Q を自動計算**（Bloch −0.93 / 反Sk +0.93 /
    メロン −0.49 / FM 0.00 と理論値に整合することを確認済）。
  - `chirality-ciss/` — 鏡像対(R/S)・らせん(P/M)・CISS(らせん電子流とスピン偏極)・
    R体vsS体で偏極反転・**分子キラリティ→界面DMI転写**・キラル分子の層間挿入・
    スピンフィルター素子。ラベルは 3D スプライトではなく **2D HTML オーバーレイ**
    （視点で切れる・重なるのを防ぐため）。
  - 注意: HTML ラベルは canvas 外なので**書き出した PNG には入らない**。図中に文字が要る
    場合は PowerPoint 側でテキストを重ねる運用。
- 2026-08-23: **監査と修正の回**。詳細は該当コミットのメッセージ参照。
  - **このリポジトリは PUBLIC**。`.gitignore` で `*.vspd *.ras *.raw *.dat` を弾いている。
    装置生データは private リポジトリ `~/Projects/skyrmion-vse2/raw-data/` が正しい置き場所。
  - `spin-texture/` `chirality-ciss/` は作られてから約3週間**コミット漏れで本番404**だった。
    トップにカードはあったのでリンク切れ状態。デプロイ済み。
  - **データ破損4件を修正**: squid の区切り文字が連続カンマを潰し Quantum Design MPMS の
    空列で列がずれていた（無言で別カラムを磁化としてプロット）/ dmm-viewer が Keithley の
    オーバーフローを実測 0 として記録 / `Math.min(...arr)` が約12.5万点で RangeError /
    squid の χ=M/H で H=0 を 0 として出力し偽のゼロ落ち。
  - **xrd の (00l) 判定を作り直した**。許容誤差を 2θ の絶対値(0.8°固定)から
    「層間距離 c の相対ずれ(%)」に変更。同じ 0.8° でも Δc/c は 2θ=5.9° で 13.5%、
    2θ=60° で 1.2% と11倍違い、(001) が来る低角でノイズを拾い放題だった。
  - **画像を 4.03MB → 0.22MB**（WebP 化）。トップの総転送量 4148KB → 265KB。
  - **板のセキュリティ**: 認証なしの curl で投稿も削除もできる状態だった。クライアントに
    匿名認証を入れ、`database.rules.json` を用意。**ただしルールは未適用** —
    Firebase の Authentication が未初期化のため、先に有効化が必要
    （手順は `database.rules.README.md`）。
- 最終コミット: 2026-05-08（DMM Monitor の Excel エクスポート / 履歴まわりの修正）
- 「作成中」タグのツールが未完成。直近の作業対象は **DMM Monitor**
- TODO（記入してください）:
  - [ ] 
  - [ ]
