# Realtime Database ルール

`database.rules.json` がこのプロジェクトの正としてのルール。

## なぜ必要だったか

2026-08-23 の監査時点で、ルールが全パス `.read: true / .write: true` 相当になっており、
**認証なしの `curl` だけでスレッドの投稿も削除もできる**状態だった（実測で確認）。
`firebaseConfig` はソースに公開されている（Firebase の設計上これは正常）ため、
ページを開いた誰でも DB URL を知ることができ、研究室メンバーの投稿を第三者が
消せてしまう。

## 何を締めたか

| パス | 読み | 書き |
|---|---|---|
| `boards/**` | 認証必須 | スレッド/レスは**投稿者本人のみ**削除・改変可。作成は認証済みなら可 |
| `boards/*/threads/*/lastActivity` | 〃 | 認証済みなら可（他人のスレへの返信で更新が要るため） |
| `profiles/**` | 認証必須 | 認証必須 |
| `crowdfund/**` | 認証必須 | 認証必須 |
| `dmm` `dmm2` `xrd` `cfms` | **公開のまま** | **公開のまま** |

クライアント側（`index.html`）は Firebase の**匿名認証**でサインインしてから
DB に触るようになっている。投稿時に `uid`（スレッド）/ `fbuid`（レス）として
認証 uid を保存し、ルールがそれを本人確認に使う。

### 既存スレッドの扱い

改修前に作られたスレッドには `uid` が無い。したがって**誰も削除できない**（安全側）。
読むことと返信することはできる。

## 残っている穴（既知・未対応）

`dmm` / `dmm2` / `xrd` / `cfms` を**公開のままにしてある**。
理由は、ラボPCの送信スクリプト（`dmm_sender.py`, `xrd_sender.py`, `cfms_sender.py`）が
`https://<db>.firebaseio.com/<path>.json` に**認証トークン無しで**書いているため、
ここを締めると計測データの送信が止まるから。

塞ぐには送信側を先に直す必要がある:

1. Firebase コンソールでサービスアカウントの鍵を発行
2. 各 sender で Google の OAuth2 トークンを取得し `?access_token=` を付ける
   （**このリポジトリは PUBLIC なので鍵をコミットしないこと**。ラボPCの環境変数に置く）
3. その後 `dmm`/`dmm2`/`xrd`/`cfms` も `auth != null` に変更

現状のリスクは「第三者が偽の測定値を注入できる」こと。板の荒らしより優先度は低いが、
残っていることは認識しておくこと。

## ⚠️ 適用前に必ずやること（未完了）

2026-08-23 時点で **この Firebase プロジェクトは Authentication が未初期化**
（API が `CONFIGURATION_NOT_FOUND` を返す）。この状態で `database.rules.json` を
適用すると匿名サインインができず、**板が誰にも読めなくなる**。

必ず次の順で行うこと:

1. Firebase コンソール → **Authentication** → 「始める」
2. Sign-in method → **匿名** を有効化
3. 本番トップを開き、DevTools のコンソールに
   `匿名認証に失敗` の警告が**出なくなった**ことを確認
4. そのうえで下記のルールを適用

クライアント側（`index.html`）は既に対応済みで、匿名認証が有効なら自動的に
それを使い、無効なら従来どおり無認証で動く（＝今この瞬間に板が壊れることはない）。
手順1〜2 を踏むまではルールを適用しないこと。

## 適用方法

Firebase コンソール → Realtime Database → ルール タブに
`database.rules.json` の中身を貼って「公開」。

CLI を使う場合:

```bash
npm i -g firebase-tools && firebase login
firebase deploy --only database --project research-tools-board
```

（`firebase.json` に `{"database": {"rules": "database.rules.json"}}` が必要）

## 変更後に必ず確認すること

```bash
# 1. 未認証では読めない（Permission denied になるはず）
curl -s "https://research-tools-board-default-rtdb.firebaseio.com/boards/tmd-viewer/threads.json?shallow=true"

# 2. 未認証では書けない（401 になるはず）
curl -s -o /dev/null -w "%{http_code}\n" -X POST -d '{"title":"x"}' \
  "https://research-tools-board-default-rtdb.firebaseio.com/boards/tmd-viewer/threads.json"

# 3. 装置パスは通ったまま（200 のはず）
curl -s -o /dev/null -w "%{http_code}\n" "https://research-tools-board-default-rtdb.firebaseio.com/dmm/status.json"
```

そのうえでブラウザで本番トップを開き、板が読めること・投稿できることを確認する。
