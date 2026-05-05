# ラボPC セットアップ手順（DMM リアルタイムモニター）

## 前提
- ラボPC: Windows（Dell）
- 接続: Keithley 2400 SourceMeter（USB シリアル / FTDIケーブル）
- 現状: デスクトップに `dmm_sender.py` だけある状態

---

## 1. 事前準備（インストール）

### Node.js（sync-server に必要。未インストールの場合）
1. https://nodejs.org/ からLTS版をダウンロード・インストール
2. インストール後、コマンドプロンプトで確認:
   ```
   node -v
   ```

### Git（未インストールの場合）
1. https://git-scm.com/download/win からダウンロード・インストール

---

## 2. リポジトリをクローン

コマンドプロンプトを開いて:
```
cd %USERPROFILE%\Desktop
git clone https://github.com/yamamoto20031117-hash/research-tools.git
```

---

## 3. dmm_sender.py の設定確認

`research-tools\dmm-monitor\dmm_sender.py` の中の設定が、現在デスクトップにある `dmm_sender.py` と同じか確認する。特に:

- `DMM_ADDRESS` — Keithley の COM ポート（例: `"ASRL3::INSTR"`）
- `WS_URL` — デフォルト `"ws://localhost:8765"` のままでOK
- `FIREBASE_URL` — 現在の値と同じか確認

もし今の `dmm_sender.py` でカスタマイズしている箇所があれば、リポジトリ版にも反映すること。

---

## 4. 起動

### デスクトップにショートカットを作成
1. `research-tools\dmm-monitor\start_all.bat` を右クリック
2. 「ショートカットの作成」→ デスクトップに移動
3. 古い `dmm_sender.py` のショートカットは削除してOK

### 起動方法
`start_all.bat` をダブルクリックするだけ。以下が自動で行われる:

1. Node.js / Python の存在チェック
2. sync-server の依存パッケージインストール（初回のみ）
3. **Sync Server** を別ウィンドウで起動（端末間グラフ共有用）
4. **DMM Sender** を起動（Keithley 2400 から測定開始）

### 停止方法
- メインウィンドウで `Ctrl+C` → Sync Server も自動停止
- または `stop.bat` をダブルクリック

---

## 5. 動作確認

1. `start_all.bat` をダブルクリック
2. 「DMM-SyncServer」という別ウィンドウが開き、`WebSocket: ws://0.0.0.0:8765` と表示される
3. メインウィンドウで Keithley に接続され、測定データが流れ始める
4. ブラウザで https://research-tools-six.vercel.app/dmm-monitor/ を開き、データが表示されることを確認
5. **別の端末（スマホ等）** で同じURLを開き、同じグラフが表示されれば同期成功

---

## 6. 今後のコード更新

自分の Mac でコードを修正・push した後、ラボPC で:
```
cd %USERPROFILE%\Desktop\research-tools
git pull
```
→ `start_all.bat` で再起動

---

## トラブルシューティング

| 症状 | 対処 |
|------|------|
| `node` が見つからない | Node.js をインストール。インストール後にコマンドプロンプトを再起動 |
| `python` が見つからない | Python インストール時に「Add Python to PATH」にチェック |
| Keithley に接続できない | `python dmm_sender.py --list` で COM ポートを確認 → `DMM_ADDRESS` を修正 |
| Sync Server に接続できない | ファイアウォールでポート 8765 を許可する |
| グラフが他端末と同期しない | Sync Server のウィンドウが起動しているか確認 |
