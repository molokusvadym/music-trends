"""STEP 2 - BUILD. Reads charts.db and writes site/index.html.

The finished page is one self-contained HTML file. Its look comes from style.css and its
behaviour (hover, dithering animation, 1-4 shortcuts) from app.js; both are copied into the page.
"""
import hashlib
import sqlite3
import sys
from html import escape
from pathlib import Path
from urllib.parse import quote

HERE = Path(__file__).parent
DB_FILE = HERE / "charts.db"
OUT_FILE = HERE / "site" / "index.html"
IMG_DIR = HERE / "site" / "img"

FONTS = ("https://fonts.googleapis.com/css2?family=Inter+Tight:wght@400;500;600&"
         "family=JetBrains+Mono:wght@400;500&family=Silkscreen&display=swap")
COUNTRY_NAMES = {"united kingdom": "the United Kingdom", "united states": "the USA"}
COUNTRY_SHORT = {"united kingdom": "UK", "united states": "USA"}


# ---------------------------------------------------------------- reading the database
def latest_date(db):
    return db.execute("SELECT MAX(snapshot_date) FROM chart_snapshots WHERE chart = 'global'").fetchone()[0]


def read_chart(db, chart, limit=20):
    """The most recent snapshot of a chart, #1 first."""
    rows = db.execute("""
        SELECT s.rank, t.name, a.name, s.playcount, s.listeners
        FROM chart_snapshots s
        JOIN tracks  t ON t.id = s.track_id
        JOIN artists a ON a.id = t.artist_id
        WHERE s.chart = ?
          AND s.snapshot_date = (SELECT MAX(snapshot_date) FROM chart_snapshots WHERE chart = ?)
        ORDER BY s.rank LIMIT ?
    """, (chart, chart, limit)).fetchall()
    return [{"rank": r[0], "name": r[1], "artist": r[2], "playcount": r[3], "listeners": r[4]} for r in rows]


def read_countries(db):
    """Country charts that have been collected (everything except the global one)."""
    return [r[0] for r in db.execute(
        "SELECT DISTINCT chart FROM chart_snapshots WHERE chart != 'global' ORDER BY chart")]


def read_top_artists(db, limit=12):
    """Artists with the most tracks on today's global top 50."""
    artists = {}
    for row in read_chart(db, "global", 50):
        entry = artists.setdefault(row["artist"], {"artist": row["artist"], "tracks": 0, "best_rank": row["rank"]})
        entry["tracks"] += 1
        entry["best_rank"] = min(entry["best_rank"], row["rank"])
    return sorted(artists.values(), key=lambda a: (-a["tracks"], a["best_rank"]))[:limit]


def read_photos(db):
    """Artist name -> photo path, but only for photos that really exist in site/img/."""
    try:
        rows = db.execute("""SELECT a.name, p.filename FROM artist_images p
                             JOIN artists a ON a.id = p.artist_id WHERE p.filename IS NOT NULL""").fetchall()
    except sqlite3.OperationalError:  # collect.py has not created that table yet
        return {}
    return {name: f"img/{filename}" for name, filename in rows if (IMG_DIR / filename).exists()}


# ---------------------------------------------------------------- building HTML pieces
def compact(n):
    """1234567 -> '1.2M'"""
    if n is None:
        return "-"
    for limit, suffix in ((1_000_000_000, "B"), (1_000_000, "M"), (1_000, "K")):
        if n >= limit:
            return f"{n / limit:.1f}".rstrip("0").rstrip(".") + suffix
    return str(n)


def attr(text):
    """Make text safe to place inside an HTML attribute."""
    return escape(str(text), quote=True)


def silhouette(seed):
    """A plain portrait silhouette, used when an artist has no photo."""
    hue = int(hashlib.md5(seed.encode("utf-8")).hexdigest(), 16) % 360
    svg = ("<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'>"
           f"<rect width='100' height='100' fill='hsl({hue},30%,64%)'/>"
           f"<circle cx='50' cy='38' r='17' fill='hsl({hue},28%,26%)'/>"
           f"<path d='M14 100c0-22 16-34 36-34s36 12 36 34z' fill='hsl({hue},28%,26%)'/></svg>")
    return "data:image/svg+xml;utf8," + quote(svg)


def item(number, title, artist, tag, photos, sub=None):
    """One row of a list. The data-* attributes are what app.js reads when you hover the row."""
    sub = artist if sub is None else sub
    image = photos.get(artist) or silhouette(artist)
    return (f'<li class="item" tabindex="0" data-seed="{attr(artist)}" data-img="{attr(image)}" '
            f'data-title="{attr(title)}" data-sub="{attr(sub)}" data-rank="{number:02d}">'
            f'<span class="n">{number:02d}</span>'
            f'<span class="t"><b>{escape(title)}</b><i>{escape(sub)}</i></span>'
            f'<span class="tag">{escape(tag)}</span></li>')


# The photo + caption shown beside every list. app.js fills it in on hover.
FIGURE = ('<div class="fig-col"><div class="fig">'
          '<div class="fig-label" data-fig>[ FIG. 01 ]</div>'
          '<div class="shot"><img alt=""><canvas aria-hidden="true"></canvas></div>'
          '<div class="caption"><b data-title></b><span data-sub></span></div></div></div>')


def section(number, section_id, title, count, items):
    """One numbered, collapsible section (the first one starts open)."""
    body = (f'<div class="split">{FIGURE}<ol class="list">{"".join(items)}</ol></div>'
            if items else '<div class="empty">[ No chart data yet ]</div>')
    return (f'<details class="acc" id="{section_id}"{" open" if number == 1 else ""}>'
            f'<summary><span>{number:02d}/</span><span>{escape(title)}</span>'
            f'<span class="count">{escape(count)}</span></summary><div class="acc-body">{body}</div></details>')


def slug(text):
    return "".join(c if c.isalnum() else "-" for c in text.lower()).strip("-")


# ---------------------------------------------------------------- the whole page
def build_page(db):
    photos = read_photos(db)
    listeners = lambda r: f"{compact(r['listeners'])} listeners"
    track_items = lambda rows: [item(r["rank"], r["name"], r["artist"], listeners(r), photos) for r in rows]

    # Each entry: (button label, html id, section title, small count text, list items)
    top_global = read_chart(db, "global")
    sections = [("Global", "global", "Top Global", f"{len(top_global)} tracks", track_items(top_global))]

    for country in read_countries(db):
        rows = read_chart(db, country)
        name = COUNTRY_NAMES.get(country, country.title())
        sections.append((COUNTRY_SHORT.get(country, country.title()), slug(country),
                         f"Top in {name}", f"{len(rows)} tracks", track_items(rows)))

    artists = read_top_artists(db)
    sections.append(("Artists", "artists", "Top Artists", f"{len(artists)} artists", [
        item(i, a["artist"], a["artist"], f"{a['tracks']} track{'s' if a['tracks'] != 1 else ''}",
             photos, sub=f"Best position #{a['best_rank']}")
        for i, a in enumerate(artists, 1)]))

    nav = "".join(f'<a href="#{sid}" data-key="{n}">[{n}] {escape(label)}</a>'
                  for n, (label, sid, *_rest) in enumerate(sections, 1))
    body = "".join(section(n, sid, title, count, items)
                   for n, (_label, sid, title, count, items) in enumerate(sections, 1))
    number_one = top_global[0]
    css = (HERE / "style.css").read_text(encoding="utf-8")
    js = (HERE / "app.js").read_text(encoding="utf-8")

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Music Trends</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="{FONTS}" rel="stylesheet"><style>{css}</style></head><body>
<header class="topbar"><div class="wrap"><a class="logo" href="#" aria-label="Home"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 2.5 1.5 11.5H4V21a1 1 0 0 0 1 1h5v-6h4v6h5a1 1 0 0 0 1-1v-9.5h2.5z"/></svg></a>
<nav class="nav">{nav}</nav></div></header>
<main class="wrap">
<section class="hero">
  <span class="plus" style="left:-8px;top:12px"></span><span class="plus" style="left:50%;top:12px"></span><span class="plus" style="right:-8px;top:12px"></span>
  <h1><span>Music</span><span class="r"><span class="hl" style="display:inline">Trends</span><span class="px" aria-hidden="true">.fm</span></span></h1>
  <p>Daily chart snapshots from Last.fm: the top tracks worldwide, in the UK and in the USA, and the artists behind them.</p>
  <span class="plus" style="left:-8px;bottom:0"></span><span class="plus" style="left:50%;bottom:0"></span><span class="plus" style="right:-8px;bottom:0"></span>
</section>
<div class="label"><span>/</span><span>Number one right now</span></div>
<div class="now"><h2>{escape(number_one['name'])}</h2>
<p><span class="hl">{escape(number_one['artist'])}</span> &nbsp; {compact(number_one['listeners'])} listeners</p></div>
{body}
</main>
<footer><div class="wrap"><div class="ruler"></div>
<p><span>Python / SQLite / Last.fm / Deezer</span><span>Press 1 to {len(sections)} to jump between sections</span><span>Updated {escape(latest_date(db))}</span></p></div></footer>
<script>{js}</script></body></html>"""


def main():
    if not DB_FILE.exists():
        print("charts.db not found. Run collect.py first.")
        return 1
    db = sqlite3.connect(DB_FILE)
    if latest_date(db) is None:
        print("No chart data yet. Run collect.py first.")
        return 1
    page = build_page(db)
    db.close()
    OUT_FILE.parent.mkdir(exist_ok=True)
    OUT_FILE.write_text(page, encoding="utf-8")
    print(f"Wrote {OUT_FILE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
