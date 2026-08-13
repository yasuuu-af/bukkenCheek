# bukkenCheek — 北千住デュエット空室ウォッチ

デュエット北千住**マキア**／**セレナ**の空室を、**毎週 月・水・金 09:00 (JST)** に自動チェックする仕組みです。

## 通知ポリシー

通知は **Discord のみ**。メールとスマホのプッシュ通知は停止しています。

**毎回投稿します**（`notify_policy: every_run`）。空室が無い日も「変化なし」の1件が届くので、投稿が無い日は仕組みが止まっているサインです。

| 状況 | 色 | 投稿内容 |
|---|---|---|
| 空室あり | 緑 | `🏠 空室が出ました` ＋ 間取り・階・面積・賃料・管理費・敷礼・入居可能日・掲載元・問い合わせ先。本文にも一行出るので通知が付く |
| 変化なし | 藍 | `変化なし` の1件（ハートビート） |
| 取得失敗 | 琥珀 | `⚠️ チェックに失敗したソースがあります` ＋ 失敗内容 |

常設ダッシュボード（URLは `docs/dashboard-url.txt`）も毎回最新に更新されます。

### Discord の設定

Webhook URL は**秘密情報**です。このリポジトリは public なので絶対にコミットしないでください（`.gitignore` 済み）。

1. Discord で 対象チャンネル → 編集 → 連携サービス → ウェブフック → 新しいウェブフック → **ウェブフックURLをコピー**
2. その URL を環境変数 `DISCORD_WEBHOOK_URL` に設定する
   （claude.ai/code の Environment 設定に入れておくと、定期実行セッションにも引き継がれます）
3. 送信テスト:

```bash
python3 scripts/notify_discord.py --status none --detail "疎通テスト" --dry-run  # 内容確認だけ
python3 scripts/notify_discord.py --status none --detail "疎通テスト"           # 実際に送信
```

## 実行

**判定はすべて Python が行います。AI は関与しません。**

```bash
python3 scripts/check_vacancy.py            # 取得→判定→Discord通知→記録更新
python3 scripts/check_vacancy.py --dry-run  # 取得と判定だけ（送信も書き込みもなし）
python3 scripts/check_vacancy.py --commit   # 記録を commit && push まで
python3 scripts/check_vacancy.py --fixture ミレアビターレ北千住   # 空室ありの動作確認
```

## ファイル構成

| ファイル | 役割 |
|---|---|
| `scripts/check_vacancy.py` | **本体。**取得・判定・差分・通知・記録を全部やる |
| `scripts/notify_discord.py` | Discord へ結果を投稿 |
| `targets.json` | 監視対象の建物とURL一覧。**追加・削除はここを編集** |
| `state.json` | 前回の空室状態。差分判定の基準 |
| `history.md` | 毎回のチェック結果ログ |
| `docs/check-procedure.md` | 判定ロジックの根拠と運用手順 |
| `docs/dashboard-url.txt` | ダッシュボードの固定URL |
| `dashboard.html` | ダッシュボードのソース |
| `.github/workflows/check-vacancy.yml` | GitHub Actions で自動実行する場合の定義 |

## 監視対象

### デュエット北千住マキア（2013年1月築 / RC5階建 / 72戸）
- [SUUMO ライブラリ](https://suumo.jp/library/tf_13/sc_13121/to_1001775437/)
- [アセットナビ 部屋一覧](https://www.assetnavi.co.jp/rent/5752/rooms)

### デュエット北千住セレナ（2005年3月築 / RC8階建 / 36戸 / 北千住駅 徒歩8分）
- [SUUMO ライブラリ](https://suumo.jp/library/tf_13/sc_13121/to_1001133916/)
- 仲介各社ページ（アイレントホーム／シティモバイル／ハウスコム）

> セレナはアセットナビに建物ページが存在しないため、SUUMO と仲介各社ページで補完しています。

## 判定ロジック

| サイト | 空室ありの目印 |
|---|---|
| SUUMO | 建物名キーワード検索（`POST /jj/common/ichiran/JJ901FC001/`）に物件カードが1件でも返る |
| アセットナビ | `<div id="room_list">` が出力される（満室時は `agreement_yet` のみ） |

> `/library/` ページは満室でも常にアーカイブ表示なので判定には使いません（足立区14棟で実測確認済み）。参照リンクとしてのみ保持しています。

取得失敗は「空室なし」と解釈せず、3回リトライしたうえで `⚠️ 取得できなかったソース` として通知します。

## 設定変更のしかた

- **物件を追加したい** → `targets.json` の `buildings` に追記
- **曜日・時刻を変えたい** → Routine（定期実行）の cron を変更
- **毎回結果がほしい** → `targets.json` の `notify_policy` を `every_run` に変更し、手順書 5. の分岐を外す
- **止めたい** → Routine を削除
