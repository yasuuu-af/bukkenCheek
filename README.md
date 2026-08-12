# bukkenCheek — 北千住デュエット空室ウォッチ

デュエット北千住**マキア**／**セレナ**の空室を、**毎週 月・水・金 09:00 (JST)** に自動チェックする仕組みです。

## 通知ポリシー

**空室が出たときだけ**通知します（変化なしの週は無音）。

- メール → tademoto.y@gmail.com
- スマホの Claude アプリへプッシュ通知
- 常設ダッシュボード（URLは `docs/dashboard-url.txt`）は毎回最新に更新

## ファイル構成

| ファイル | 役割 |
|---|---|
| `targets.json` | 監視対象の建物とURL一覧。**追加・削除はここを編集** |
| `state.json` | 前回の空室状態。差分判定の基準 |
| `history.md` | 毎回のチェック結果ログ |
| `docs/check-procedure.md` | 定期セッションが毎回実行する手順書 |
| `docs/dashboard-url.txt` | ダッシュボードの固定URL |
| `dashboard.html` | ダッシュボードのソース |

## 監視対象

### デュエット北千住マキア（2013年1月築 / RC5階建 / 72戸）
- [SUUMO ライブラリ](https://suumo.jp/library/tf_13/sc_13121/to_1001775437/)
- [アセットナビ 部屋一覧](https://www.assetnavi.co.jp/rent/5752/rooms)

### デュエット北千住セレナ（2005年3月築 / RC8階建 / 36戸 / 北千住駅 徒歩8分）
- [SUUMO ライブラリ](https://suumo.jp/library/tf_13/sc_13121/to_1001133916/)
- 仲介各社ページ（アイレントホーム／シティモバイル／ハウスコム）

> セレナはアセットナビに建物ページが存在しないため、SUUMO と仲介各社ページで補完しています。

## 設定変更のしかた

- **物件を追加したい** → `targets.json` の `buildings` に追記
- **曜日・時刻を変えたい** → Routine（定期実行）の cron を変更
- **毎回結果がほしい** → `targets.json` の `notify_policy` を `every_run` に変更し、手順書 5. の分岐を外す
- **止めたい** → Routine を削除
