#!/usr/bin/env python3
"""デュエット北千住マキア／セレナの空室チェック。

AI は関与しない。このスクリプト単体で、取得・判定・差分・Discord通知・記録更新まで行う。

  python3 scripts/check_vacancy.py              # 本番実行（Discord送信あり、コミットなし）
  python3 scripts/check_vacancy.py --dry-run    # 取得と判定だけ。送信も書き込みもしない
  python3 scripts/check_vacancy.py --commit     # 記録を更新して git commit && push まで行う
  python3 scripts/check_vacancy.py --fixture ミレアビターレ北千住   # 空室ありの動作確認

判定の根拠（実際のHTMLで検証済み）:
  SUUMO    … 建物名キーワード検索 POST /jj/common/ichiran/JJ901FC001/ の結果に
              物件カードが1件でもあれば掲載中。0件なら募集なし。
              ※ /library/ ページは満室でも常に「過去の掲載情報を元に作成しています」と
                出るだけで募集状況を反映しないため、判定には使わない。
  アセットナビ … 空室があるときだけ <div id="room_list"> が出る。満室時は
              id="agreement_yet"（満室一覧）のみ。部屋行の <tr> に
              data-current(階) data-roomplan(間取り) data-space(面積) data-price(賃料) が入る。
"""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import pathlib
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
TARGETS = ROOT / "targets.json"
STATE = ROOT / "state.json"
HISTORY = ROOT / "history.md"

SUUMO_SEARCH = "https://suumo.jp/jj/common/ichiran/JJ901FC001/"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
JST = dt.timezone(dt.timedelta(hours=9))

TIMEOUT = 45
RETRIES = 3


class FetchError(Exception):
    """取得に失敗した。空室なしとは決して解釈しないこと。"""


# ────────────────────────────────────────────────────────────── 取得

def fetch(url: str, data: dict | None = None) -> str:
    body = urllib.parse.urlencode(data).encode() if data else None
    last = None
    for attempt in range(1, RETRIES + 1):
        try:
            req = urllib.request.Request(
                url, data=body,
                headers={"User-Agent": UA, "Accept-Language": "ja,en;q=0.8"},
            )
            with urllib.request.urlopen(req, timeout=TIMEOUT) as res:
                return res.read().decode("utf-8", "replace")
        except (urllib.error.URLError, urllib.error.HTTPError, OSError) as e:
            last = e
            if attempt < RETRIES:
                import time
                time.sleep(2 ** attempt)
    raise FetchError(f"{url}: {last}")


def strip_comments(s: str) -> str:
    return re.sub(r"(?s)<!--.*?-->", "", s)


def text_of(fragment: str) -> str:
    s = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", fragment))).strip()
    # SUUMO は「15.46m<sup>2</sup>」なので、タグを剥がすと "15.46m 2" になる
    return re.sub(r"m\s*2(?![0-9])", "m²", s)


# ────────────────────────────────────────────────────────────── SUUMO

CARD_RE = re.compile(
    r'(?s)<li class="cassette js-bukkenCassette">(.*?)(?=<li class="cassette js-bukkenCassette">|</ul>)'
)


def check_suumo(building_name: str, keyword: str) -> list[dict]:
    """SUUMOの建物名検索から、その建物の掲載中の部屋を返す。"""
    page = fetch(SUUMO_SEARCH, {"ar": "030", "bs": "040", "kwd": keyword})
    rooms = []
    for card in CARD_RE.findall(page):
        # カードの説明文に建物名が入っている。similar-name の取り違えを防ぐため厳密照合する。
        blurb = text_of("".join(re.findall(r'(?s)<p class="cassettebox-txt">(.*?)</p>', card)))
        if building_name not in blurb:
            continue

        link = re.search(r'href="(/chintai/[a-z]+_\d+/)"', card)
        if not link:
            continue

        detail = {}
        for dt_, dd_ in re.findall(r"(?s)<dt[^>]*>(.*?)</dt>\s*<dd[^>]*>(.*?)</dd>", card):
            detail[text_of(dt_).rstrip("：")] = text_of(dd_)

        title = re.search(r'(?s)<h2 class="cassettebox-title">.*?<a[^>]*>(.*?)</a>', card)

        rooms.append({
            "source": "SUUMO",
            "id": link.group(1).strip("/").split("_")[-1],
            "url": "https://suumo.jp" + link.group(1),
            "rent": detail.get("賃料", ""),
            "admin": detail.get("管理・共益費", ""),
            "deposit": detail.get("礼金/敷金", ""),
            "area": detail.get("専有面積", "").replace("m2", "m²"),
            "plan": detail.get("間取り", ""),
            "floor": "",  # 検索結果カードに階の情報は無い。詳細ページで確認する。
            "headline": text_of(title.group(1)) if title else "",
        })
    return rooms


# ────────────────────────────────────────────────────────────── アセットナビ

def check_assetnavi(url: str) -> list[dict]:
    """アセットナビの部屋一覧から募集中の部屋を返す。満室なら空リスト。"""
    page = strip_comments(fetch(url))

    if 'id="room_list"' not in page:
        return []          # 満室。空室セクションそのものが出力されない。

    block = re.search(r'(?s)<div id="room_list".*?(?=<div id="agreement_yet"|</div>\s*</div>\s*$)', page)
    block = block.group(0) if block else page

    base = re.match(r"(https://[^/]+)", url).group(1)
    rooms = []
    for tr in re.findall(r"(?s)<tr\b([^>]*)>(.*?)</tr>", block):
        attrs, inner = tr
        price = re.search(r'data-price="(\d+)"', attrs)
        if not price:
            continue
        plan = re.search(r'data-roomplan="([^"]*)"', attrs)
        space = re.search(r'data-space="([^"]*)"', attrs)
        cur = re.search(r'data-current="([^"]*)"', attrs)
        rid = re.search(r'href="(/rent/\d+/(\d+))"', inner)

        yen = int(price.group(1))
        rooms.append({
            "source": "アセットナビ",
            "id": rid.group(2) if rid else f"{cur.group(1) if cur else '?'}-{price.group(1)}",
            "url": base + rid.group(1) if rid else url,
            "rent": f"{yen:,}円",
            "admin": "",
            "deposit": "",
            "area": f"{space.group(1)}m²" if space else "",
            "plan": plan.group(1) if plan else "",
            "floor": f"{cur.group(1)}階" if cur else "",
            "headline": "",
        })
    return rooms


# ────────────────────────────────────────────────────────────── 判定

def check_building(b: dict, fixture: str | None) -> dict:
    name = b["name"]
    keyword = fixture or b["suumo_keyword"]
    result = {"id": b["id"], "name": name, "rooms": [], "errors": []}

    try:
        result["rooms"] += check_suumo(fixture or name, keyword)
    except FetchError as e:
        result["errors"].append(f"SUUMO: {e}")

    if b.get("assetnavi_rooms"):
        try:
            result["rooms"] += check_assetnavi(b["assetnavi_rooms"])
        except FetchError as e:
            result["errors"].append(f"アセットナビ: {e}")

    result["vacancy"] = bool(result["rooms"])
    return result


def room_key(r: dict) -> str:
    return f"{r['source']}:{r['id']}"


# ────────────────────────────────────────────────────────────── 出力

MAX_ROWS = 8   # Discord の embed は 4096 文字上限。多すぎる回は上位だけ載せる。


def render_rooms(rooms: list[dict]) -> str:
    shown, rest = rooms[:MAX_ROWS], rooms[MAX_ROWS:]
    lines = ["| 間取り | 階 | 面積 | 賃料 | 管理費 | 敷/礼 | リンク |",
             "|---|---|---|---|---|---|---|"]
    for r in shown:
        lines.append("| {plan} | {floor} | {area} | {rent} | {admin} | {deposit} | [{source}]({url}) |".format(
            plan=r["plan"] or "—", floor=r["floor"] or "—", area=r["area"] or "—",
            rent=r["rent"] or "—", admin=r["admin"] or "—", deposit=r["deposit"] or "—",
            source=r["source"], url=r["url"]))
    if rest:
        lines.append(f"\nほか {len(rest)}件（全件はダッシュボードと各サイトで確認してください）")
    return "\n".join(lines)


def build_report(results: list[dict], prev: dict) -> tuple[str, str, str]:
    """(status, headline, detail) を返す。"""
    errors = [f"{r['name']} … {e}" for r in results for e in r["errors"]]
    vacant = [r for r in results if r["vacancy"]]

    if vacant:
        new_rooms = []
        for r in vacant:
            seen = set(prev.get("buildings", {}).get(r["id"], {}).get("room_keys", []))
            new_rooms += [x for x in r["rooms"] if room_key(x) not in seen]

        first = (new_rooms or vacant[0]["rooms"])[0]
        owner = next(r["name"] for r in vacant if first in r["rooms"])
        headline = " ".join(x for x in [owner, first["plan"], first["floor"], first["rent"]] if x)

        parts = []
        for r in vacant:
            parts.append(f"**{r['name']}** … 募集中 {len(r['rooms'])}件\n{render_rooms(r['rooms'])}")
        for r in results:
            if not r["vacancy"] and not r["errors"]:
                parts.append(f"**{r['name']}** … 空室なし")
        if new_rooms:
            parts.append(f"うち **{len(new_rooms)}件が新規**（前回チェック時にはありませんでした）")
        if errors:
            parts.append("⚠️ 取得できなかったソース:\n" + "\n".join(f"・{e}" for e in errors))
        return "vacant", headline, "\n\n".join(parts)

    if errors and all(r["errors"] for r in results):
        return "error", "全ソースの取得に失敗しました", "\n".join(f"・{e}" for e in errors)

    detail = "\n".join(f"・{r['name']} … 空室なし" for r in results if not r["errors"])
    if errors:
        detail += "\n\n⚠️ 取得できなかったソース:\n" + "\n".join(f"・{e}" for e in errors)
        return "error", "一部のソースを取得できませんでした", detail
    return "none", "", detail


# ────────────────────────────────────────────────────────────── 記録

def write_state(results: list[dict], status: str, now: dt.datetime, prev: dict) -> dict:
    state = {
        "last_checked": now.isoformat(),
        "last_change_detected": prev.get("last_change_detected"),
        "buildings": {},
    }
    if status == "vacant":
        state["last_change_detected"] = now.isoformat()
    for r in results:
        state["buildings"][r["id"]] = {
            "name": r["name"],
            "vacancy": r["vacancy"],
            "room_keys": sorted(room_key(x) for x in r["rooms"]),
            "available_rooms": r["rooms"],
            "errors": r["errors"],
        }
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return state


def append_history(results: list[dict], status: str, now: dt.datetime) -> None:
    cells = []
    for r in results:
        if r["errors"] and not r["rooms"]:
            cells.append("取得失敗")
        elif r["vacancy"]:
            cells.append(f"**空室{len(r['rooms'])}件**")
        else:
            cells.append("空室なし")
    change = {"vacant": "🏠 空室あり", "error": "⚠️ 取得失敗あり", "none": "—"}[status]
    row = f"| {now:%Y-%m-%d %H:%M} | {' | '.join(cells)} | {change} |\n"
    with HISTORY.open("a", encoding="utf-8") as f:
        f.write(row)


def git_commit(now: dt.datetime, status: str) -> None:
    label = {"vacant": "空室あり", "error": "取得失敗あり", "none": "変化なし"}[status]
    branch = "claude/kitasenjuku-property-check-gm5imz"
    cmds = [
        ["git", "add", "state.json", "history.md", "docs/index.html"],
        ["git", "-c", "user.name=bukkencheek-bot", "-c", "user.email=noreply@anthropic.com",
         "commit", "-m", f"chore: 空室チェック {now:%Y-%m-%d}（{label}）"],
        ["git", "push", "origin", f"HEAD:{branch}"],
    ]
    for c in cmds:
        p = subprocess.run(c, cwd=ROOT, capture_output=True, text=True)
        if p.returncode != 0:
            if "nothing to commit" in (p.stdout + p.stderr):
                print("記録に変化なし。コミットは省略しました。")
                return
            print(f"git 失敗: {' '.join(c)}\n{p.stdout}{p.stderr}", file=sys.stderr)
            return
    print("記録をコミットして push しました。")


# ────────────────────────────────────────────────────────────── 本体

def main() -> int:
    ap = argparse.ArgumentParser(description="デュエット北千住の空室チェック")
    ap.add_argument("--dry-run", action="store_true", help="送信も書き込みもしない")
    ap.add_argument("--commit", action="store_true", help="記録を更新して commit && push する")
    ap.add_argument("--fixture", metavar="建物名",
                    help="動作確認用。SUUMO検索をこの名前で行い、空室ありの経路を通す")
    args = ap.parse_args()

    cfg = json.loads(TARGETS.read_text(encoding="utf-8"))
    prev = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}
    now = dt.datetime.now(JST)

    results = [check_building(b, args.fixture) for b in cfg["buildings"]]
    status, headline, detail = build_report(results, prev)

    print(f"[{now:%Y-%m-%d %H:%M}] status={status}")
    for r in results:
        print(f"  {r['name']}: 空室{len(r['rooms'])}件"
              + (f" / エラー{len(r['errors'])}件" if r["errors"] else ""))
    if headline:
        print(f"  → {headline}")

    if args.dry_run:
        print("\n--- dry-run のためここで終了（Discord送信なし・ファイル更新なし）---")
        print(detail)
        return 0

    # Discord は毎回送る（notify_policy: every_run）。投稿が無い日は故障のサイン。
    notify = [sys.executable, str(ROOT / "scripts" / "notify_discord.py"),
              "--status", status, "--detail", detail, "--checked-at", now.isoformat()]
    if headline:
        notify += ["--headline", headline]
    p = subprocess.run(notify, capture_output=True, text=True)
    print(p.stdout.strip() or p.stderr.strip())
    discord_ok = p.returncode == 0

    write_state(results, status, now, prev)
    append_history(results, status, now)

    # 公開ダッシュボード（GitHub Pages）を最新の state から作り直す
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "render_dashboard.py")],
                       capture_output=True, text=True, cwd=ROOT)
    print(r.stdout.strip() or r.stderr.strip())

    if args.commit:
        git_commit(now, status)

    return 0 if discord_ok else 1


if __name__ == "__main__":
    sys.exit(main())
