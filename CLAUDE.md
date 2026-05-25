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
| `xrd-plotter/` | XRD データプロッター | 公開 |
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

- 最終コミット: 2026-05-08（DMM Monitor の Excel エクスポート / 履歴まわりの修正）
- 「作成中」タグのツールが未完成。直近の作業対象は **DMM Monitor**
- TODO（記入してください）:
  - [ ] 
  - [ ]
