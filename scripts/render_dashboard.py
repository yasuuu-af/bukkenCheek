#!/usr/bin/env python3
"""state.json から公開ダッシュボード docs/index.html を生成する。

GitHub Pages で配信する前提。check_vacancy.py が毎回これを呼ぶので、
チェックが走るたびにページの中身が最新になる。
"""

from __future__ import annotations

import datetime as dt
import html
import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
STATE = ROOT / "state.json"
TARGETS = ROOT / "targets.json"
HISTORY = ROOT / "history.md"
OUT = ROOT / "docs" / "index.html"

JST = dt.timezone(dt.timedelta(hours=9))
E = html.escape


def next_runs(now: dt.datetime, count: int = 4) -> list[dt.datetime]:
    """月(0)・水(2)・金(4) 09:00 JST の次回以降を返す。"""
    out, d = [], now.replace(hour=9, minute=0, second=0, microsecond=0)
    if d <= now:
        d += dt.timedelta(days=1)
    while len(out) < count:
        if d.weekday() in (0, 2, 4):
            out.append(d)
        d += dt.timedelta(days=1)
    return out


def history_rows(limit: int = 12) -> list[list[str]]:
    if not HISTORY.exists():
        return []
    rows = []
    for line in HISTORY.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line.startswith("|") or set(line) <= set("|- "):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if cells and cells[0].startswith("日時"):
            continue
        rows.append(cells)
    return rows[::-1][:limit]


def md_inline(s: str) -> str:
    """履歴セルの **強調** だけ通す。"""
    return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", E(s))


def room_table(rooms: list[dict]) -> str:
    if not rooms:
        return ""
    head = ("<div class='scroll'><table><thead><tr>"
            "<th>間取り</th><th>階</th><th>面積</th><th>賃料</th><th>管理費</th><th>敷/礼</th><th>掲載元</th>"
            "</tr></thead><tbody>")
    body = "".join(
        "<tr><td>{}</td><td>{}</td><td>{}</td><td class='num'>{}</td><td class='num'>{}</td><td>{}</td>"
        "<td><a href='{}'>{}</a></td></tr>".format(
            E(r.get("plan") or "—"), E(r.get("floor") or "—"), E(r.get("area") or "—"),
            E(r.get("rent") or "—"), E(r.get("admin") or "—"), E(r.get("deposit") or "—"),
            E(r.get("url", "#")), E(r.get("source", "リンク")))
        for r in rooms)
    return head + body + "</tbody></table></div>"


def build() -> str:
    state = json.loads(STATE.read_text(encoding="utf-8"))
    cfg = json.loads(TARGETS.read_text(encoding="utf-8"))
    now = dt.datetime.now(JST)

    checked = state.get("last_checked", "")
    try:
        checked_disp = dt.datetime.fromisoformat(checked).strftime("%Y-%m-%d %H:%M")
    except ValueError:
        checked_disp = checked or "—"

    buildings = state.get("buildings", {})
    any_vacant = any(b.get("vacancy") for b in buildings.values())
    any_error = any(b.get("errors") for b in buildings.values())

    if any_vacant:
        vstate, vline = "vacant", "空室が出ています"
    elif any_error:
        vstate, vline = "warn", "一部のソースを取得できませんでした"
    else:
        vstate, vline = "full", "現在、両物件とも空室なし"

    meta = {b["id"]: b for b in cfg["buildings"]}

    cards = []
    for bid, b in buildings.items():
        m = meta.get(bid, {})
        vacant = b.get("vacancy")
        errs = b.get("errors") or []
        chip = ("vacant", f"空室{len(b.get('available_rooms', []))}件") if vacant else \
               (("warn", "取得失敗") if errs else ("full", "満室"))

        links = []
        if m.get("suumo_library"):
            links.append(("SUUMO 建物ページ", m["suumo_library"]))
        if m.get("assetnavi_rooms"):
            links.append(("アセットナビ 部屋一覧", m["assetnavi_rooms"]))
        for a in m.get("agency_pages", []):
            links.append(("仲介ページ", a))

        src = "".join(
            f"<div class='source'><a href='{E(u)}'>{E(label)}</a>"
            f"<span class='source-state'>{'募集あり' if vacant else '募集中の部屋なし'}</span></div>"
            for label, u in links)

        err_html = ("<p class='note note--warn'>⚠️ " +
                    "<br>".join(E(x) for x in errs) + "</p>") if errs else ""

        cards.append(f"""
    <article class="card">
      <div class="card-head">
        <div>
          <h3 class="card-name">{E(b.get('name', bid))}</h3>
          <p class="card-spec">{E(m.get('spec', ''))}</p>
        </div>
        <span class="chip" data-state="{chip[0]}">{E(chip[1])}</span>
      </div>
      {room_table(b.get('available_rooms', []))}
      <div class="sources">{src}</div>
      {err_html}
    </article>""")

    slots = "".join(
        f"<div class='slot' data-next='{str(i == 0).lower()}'>"
        f"<div class='slot-day'>{'月火水木金土日'[d.weekday()]}曜</div>"
        f"<div class='slot-when'>{d:%m/%d} 09:00{' · 次回' if i == 0 else ''}</div></div>"
        for i, d in enumerate(next_runs(now)))

    hrows = "".join(
        "<tr>" + "".join(f"<td>{md_inline(c)}</td>" for c in row) + "</tr>"
        for row in history_rows())

    return TEMPLATE.format(
        vstate=vstate, vline=E(vline), checked=E(checked_disp),
        cards="".join(cards), slots=slots, hrows=hrows,
        generated=f"{now:%Y-%m-%d %H:%M}")


TEMPLATE = """<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>北千住デュエット空室ボード</title>
<meta name="description" content="デュエット北千住マキア・セレナの空室状況。月・水・金 09:00 に自動チェック。">
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16'><text y='14' font-size='14'>&#127968;</text></svg>">
<style>
:root{{--paper:#EFF1F5;--card:#FFF;--card-sunk:#F6F7FA;--ink:#151A22;--ink-soft:#4B5568;
--ink-faint:#79839A;--rule:#DDE1EA;--rule-soft:#E9ECF2;--ai:#27467E;--ai-wash:#E4EAF5;
--vacant:#0E7A57;--vacant-wash:#DDF0E7;--full:#6C7689;--full-wash:#E6E9EF;--warn:#A2570A;
--warn-wash:#F7EBD9;--shadow:0 1px 2px rgba(21,26,34,.06),0 8px 24px -14px rgba(21,26,34,.28);
--gothic:"Hiragino Kaku Gothic ProN","Hiragino Sans","Yu Gothic Medium","Yu Gothic","Noto Sans JP",Meiryo,system-ui,sans-serif;
--data:ui-monospace,"SF Mono",SFMono-Regular,Menlo,Consolas,"Yu Gothic",monospace;}}
@media(prefers-color-scheme:dark){{:root:not([data-theme="light"]){{--paper:#0F131A;--card:#171C25;
--card-sunk:#1D232E;--ink:#E7EAF0;--ink-soft:#A6AFC0;--ink-faint:#7B8598;--rule:#2A313E;
--rule-soft:#232A35;--ai:#8FAEE4;--ai-wash:#1C2739;--vacant:#4FC79B;--vacant-wash:#13302A;
--full:#8B94A6;--full-wash:#232A35;--warn:#E0A455;--warn-wash:#33270F;
--shadow:0 1px 2px rgba(0,0,0,.4),0 8px 24px -14px rgba(0,0,0,.8);}}}}
:root[data-theme="dark"]{{--paper:#0F131A;--card:#171C25;--card-sunk:#1D232E;--ink:#E7EAF0;
--ink-soft:#A6AFC0;--ink-faint:#7B8598;--rule:#2A313E;--rule-soft:#232A35;--ai:#8FAEE4;
--ai-wash:#1C2739;--vacant:#4FC79B;--vacant-wash:#13302A;--full:#8B94A6;--full-wash:#232A35;
--warn:#E0A455;--warn-wash:#33270F;--shadow:0 1px 2px rgba(0,0,0,.4),0 8px 24px -14px rgba(0,0,0,.8);}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--paper);color:var(--ink);font-family:var(--gothic);
font-size:15px;line-height:1.7;-webkit-font-smoothing:antialiased}}
.wrap{{max-width:60rem;margin:0 auto;padding:clamp(1.75rem,4vw,3.25rem) clamp(1rem,4vw,2rem) 4rem;
display:flex;flex-direction:column;gap:2.25rem}}
.eyebrow{{font-family:var(--data);font-size:.6875rem;letter-spacing:.14em;text-transform:uppercase;color:var(--ink-faint)}}
h1{{margin:0;font-size:clamp(1.5rem,4.5vw,2rem);font-weight:700;letter-spacing:.01em;line-height:1.25;text-wrap:balance}}
.masthead{{display:flex;flex-direction:column;gap:.5rem}}
.sub{{margin:0;color:var(--ink-soft);font-size:.875rem}}
.verdict{{display:flex;flex-wrap:wrap;align-items:baseline;gap:.5rem 1rem;padding:1.25rem 1.5rem;
border-radius:4px;border:1px solid var(--rule);border-left:4px solid var(--full);
background:var(--card);box-shadow:var(--shadow)}}
.verdict[data-state="vacant"]{{border-left-color:var(--vacant);background:var(--vacant-wash)}}
.verdict[data-state="warn"]{{border-left-color:var(--warn);background:var(--warn-wash)}}
.verdict-line{{margin:0;font-size:1.25rem;font-weight:700;letter-spacing:.01em}}
.verdict[data-state="vacant"] .verdict-line{{color:var(--vacant)}}
.verdict-meta{{margin:0;font-family:var(--data);font-size:.75rem;color:var(--ink-soft);font-variant-numeric:tabular-nums}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(19rem,1fr));gap:1rem}}
.card,.panel{{display:flex;flex-direction:column;gap:.875rem;padding:1.25rem 1.375rem 1.375rem;
background:var(--card);border:1px solid var(--rule);border-radius:4px;box-shadow:var(--shadow)}}
.card-head{{display:flex;align-items:flex-start;justify-content:space-between;gap:.75rem}}
.card-name{{margin:0;font-size:1.0625rem;font-weight:700;letter-spacing:.01em}}
.card-spec{{margin:.125rem 0 0;font-family:var(--data);font-size:.6875rem;color:var(--ink-faint);font-variant-numeric:tabular-nums}}
.chip{{flex-shrink:0;font-family:var(--data);font-size:.6875rem;font-weight:600;letter-spacing:.06em;
padding:.1875rem .5rem;border-radius:2px;white-space:nowrap}}
.chip[data-state="full"]{{color:var(--full);background:var(--full-wash)}}
.chip[data-state="vacant"]{{color:var(--vacant);background:var(--vacant-wash)}}
.chip[data-state="warn"]{{color:var(--warn);background:var(--warn-wash)}}
.sources{{display:flex;flex-direction:column;gap:1px;background:var(--rule-soft);border-radius:3px;overflow:hidden}}
.source{{display:flex;align-items:baseline;justify-content:space-between;gap:.75rem;
padding:.5625rem .75rem;background:var(--card-sunk);font-size:.8125rem}}
a{{color:var(--ai);text-decoration:none;border-bottom:1px solid transparent}}
a:hover{{border-bottom-color:currentColor}}
a:focus-visible{{outline:2px solid var(--ai);outline-offset:2px;border-radius:2px}}
.source-state{{color:var(--ink-soft);font-size:.75rem;text-align:right}}
.note{{margin:0;font-size:.75rem;color:var(--ink-faint);line-height:1.6}}
.note--warn{{color:var(--warn)}}
h2{{margin:0;font-family:var(--data);font-size:.6875rem;letter-spacing:.14em;text-transform:uppercase;
color:var(--ink-faint);font-weight:600}}
.rail{{display:flex;flex-wrap:wrap;gap:.5rem}}
.slot{{flex:1 1 7rem;padding:.625rem .75rem;border:1px solid var(--rule);border-radius:3px;background:var(--card-sunk)}}
.slot[data-next="true"]{{border-color:var(--ai);background:var(--ai-wash)}}
.slot-day{{font-size:.875rem;font-weight:700}}
.slot-when{{font-family:var(--data);font-size:.6875rem;color:var(--ink-faint);font-variant-numeric:tabular-nums}}
.slot[data-next="true"] .slot-when{{color:var(--ai);font-weight:600}}
.scroll{{overflow-x:auto}}
table{{width:100%;border-collapse:collapse;font-size:.8125rem}}
th,td{{padding:.5rem .75rem;text-align:left;border-bottom:1px solid var(--rule-soft);white-space:nowrap}}
th{{font-family:var(--data);font-size:.6875rem;letter-spacing:.08em;text-transform:uppercase;
color:var(--ink-faint);font-weight:600}}
td.num,tbody td:first-child{{font-variant-numeric:tabular-nums}}
.panel tbody td:first-child{{font-family:var(--data);color:var(--ink-soft)}}
tr:last-child td{{border-bottom:none}}
footer{{color:var(--ink-faint);font-size:.75rem;line-height:1.7;border-top:1px solid var(--rule);padding-top:1.25rem}}
footer p{{margin:0 0 .375rem}}
</style>
</head>
<body>
<div class="wrap">

  <header class="masthead">
    <span class="eyebrow">Kita-Senju · Duet Series</span>
    <h1>北千住デュエット空室ボード</h1>
    <p class="sub">デュエット北千住マキア・セレナの空室を 月・水・金 09:00 (JST) に自動チェックしています。</p>
  </header>

  <section class="verdict" data-state="{vstate}">
    <p class="verdict-line">{vline}</p>
    <p class="verdict-meta">最終チェック {checked} JST</p>
  </section>

  <section class="grid">{cards}
  </section>

  <section class="panel">
    <h2>チェック予定</h2>
    <div class="rail">{slots}</div>
  </section>

  <section class="panel">
    <h2>チェック履歴</h2>
    <div class="scroll">
      <table>
        <thead><tr><th>日時 (JST)</th><th>マキア</th><th>セレナ</th><th>変化</th></tr></thead>
        <tbody>{hrows}</tbody>
      </table>
    </div>
  </section>

  <footer>
    <p>このページはチェックが走るたびに自動更新されます（生成 {generated} JST）。</p>
    <p>空室の有無にかかわらず毎回 Discord に通知が届きます。投稿が無い日は仕組みが止まっているサインです。</p>
    <p><a href="https://github.com/yasuuu-af/bukkenCheek">ソースと履歴（GitHub）</a></p>
  </footer>

</div>
</body>
</html>
"""


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(build(), encoding="utf-8")
    print(f"ダッシュボードを生成しました: {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
