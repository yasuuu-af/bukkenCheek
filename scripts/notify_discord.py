#!/usr/bin/env python3
"""空室チェック結果を Discord に通知する。

Webhook URL の解決順（先に見つかったものを使う）:
  1. 環境変数 DISCORD_WEBHOOK_URL
  2. ~/.config/bukkencheek/discord-webhook

このリポジトリは public なので、Webhook URL は絶対にコミットしないこと。

使い方:
  python3 scripts/notify_discord.py \
      --status vacant \
      --headline "デュエット北千住マキア 1LDK 3階 128,000円" \
      --detail "$(cat detail.md)"

  python3 scripts/notify_discord.py --status none            # 変化なしの軽い1行
  python3 scripts/notify_discord.py --status error --detail "SUUMO が 503"
  python3 scripts/notify_discord.py --status vacant ... --dry-run   # 送信せず内容確認
"""

import argparse
import json
import os
import pathlib
import sys
import urllib.error
import urllib.request

DASHBOARD_URL = "https://claude.ai/code/artifact/54381015-6267-4a8f-b6d3-4db54ad305c2"
REPO_URL = "https://github.com/yasuuu-af/bukkenCheek"

# 空室あり=緑（良い知らせ）／変化なし=藍／取得失敗=琥珀
STYLES = {
    "vacant": {"color": 0x0E7A57, "title": "🏠 空室が出ました"},
    "none":   {"color": 0x27467E, "title": "変化なし"},
    "error":  {"color": 0xA2570A, "title": "⚠️ チェックに失敗したソースがあります"},
}

CONFIG_PATH = pathlib.Path.home() / ".config" / "bukkencheek" / "discord-webhook"


def resolve_webhook() -> str:
    url = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()
    if url:
        return url
    if CONFIG_PATH.is_file():
        url = CONFIG_PATH.read_text(encoding="utf-8").strip()
        if url:
            return url
    sys.exit(
        "Discord Webhook URL が見つかりません。\n"
        "  環境変数 DISCORD_WEBHOOK_URL を設定するか、\n"
        f"  {CONFIG_PATH} に URL を1行で保存してください。"
    )


def build_payload(status: str, headline: str, detail: str, checked_at: str) -> dict:
    style = STYLES[status]

    description_parts = []
    if headline:
        description_parts.append(f"**{headline}**")
    if detail:
        description_parts.append(detail)
    description = "\n\n".join(description_parts)

    # Discord の embed description は 4096 文字上限
    if len(description) > 4000:
        description = description[:3900] + "\n\n…（以下省略。ダッシュボード参照）"

    embed = {
        "title": style["title"],
        "color": style["color"],
        "description": description or "—",
        "url": DASHBOARD_URL,
        "fields": [
            {"name": "物件", "value": "デュエット北千住 マキア / セレナ", "inline": True},
            {"name": "チェック日時", "value": checked_at or "—", "inline": True},
        ],
        "footer": {"text": "北千住デュエット空室ウォッチ · 月・水・金 09:00 JST"},
    }
    if checked_at:
        embed["timestamp"] = checked_at

    payload = {
        "username": "空室ウォッチ",
        "embeds": [embed],
    }
    # 空室が出たときだけ本文でも呼びかける（変化なしの回は無音にしたいので付けない）
    if status == "vacant":
        payload["content"] = f"空室が出ました。 <{DASHBOARD_URL}>"
    return payload


def post(webhook: str, payload: dict) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        webhook,
        data=body,
        headers={"Content-Type": "application/json", "User-Agent": "bukkencheek/1.0"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as res:
            print(f"Discord へ送信しました (HTTP {res.status})")
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:500]
        sys.exit(f"Discord への送信に失敗しました (HTTP {e.code}): {detail}")
    except urllib.error.URLError as e:
        sys.exit(f"Discord に接続できませんでした: {e.reason}")


def main() -> None:
    p = argparse.ArgumentParser(description="空室チェック結果を Discord に通知する")
    p.add_argument("--status", required=True, choices=sorted(STYLES))
    p.add_argument("--headline", default="", help="1行の見出し。空室ありのときは 建物名 間取り 階 賃料")
    p.add_argument("--detail", default="", help="本文（Discord のマークダウンが使えます）")
    p.add_argument("--checked-at", default="", help="ISO8601 のチェック日時")
    p.add_argument("--dry-run", action="store_true", help="送信せず payload を表示する")
    args = p.parse_args()

    payload = build_payload(args.status, args.headline, args.detail, args.checked_at)

    if args.dry_run:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    post(resolve_webhook(), payload)


if __name__ == "__main__":
    main()
