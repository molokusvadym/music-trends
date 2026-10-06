"""STEP 1 - COLLECT. Run once a day (run.bat does it for you).

What it does:
  1. Asks Last.fm for today's top 50 tracks: worldwide, UK and USA.
  2. Saves them in charts.db (a SQLite database file), one snapshot per day.
  3. Looks up a photo for each new artist on Deezer and saves it in site/img/.

Only Python's built-in libraries are used, so there is nothing to install.
"""
import json
import re
import sqlite3
import sys
import time
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

HERE = Path(__file__).parent          # the folder this file lives in
DB_FILE = HERE / "charts.db"
IMG_DIR = HERE / "site" / "img"       # artist photos are saved here
COUNTRIES = ["united kingdom", "united states"]
LIMIT = 50                            # tracks per chart


# ---------------------------------------------------------------- talking to websites
def read_api_key():
    """Read LASTFM_API_KEY from the .env file next to this script."""
    env_file = HERE / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("LASTFM_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"')
    return None


def fetch_json(url, params=None):
    """Download a web address and return its JSON answer as Python data."""
    if params:
        url += "?" + urllib.parse.urlencode(params)
    request = urllib.request.Request(url, headers={"User-Agent": "MusicTrends/1.0"})
    with urllib.request.urlopen(request, timeout=15) as response:
        return json.load(response)


def to_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def get_chart(api_key, method, **extra):
    """Ask Last.fm for a chart. Returns a list of tracks, #1 first."""
    data = fetch_json("https://ws.audioscrobbler.com/2.0/", {
        "method": method, "api_key": api_key, "format": "json", "limit": LIMIT, **extra,
    })
    if "error" in data:  # Last.fm reports problems inside a normal-looking answer
        raise RuntimeError(f"Last.fm error {data['error']}: {data.get('message')}")
    tracks = data.get("tracks", {}).get("track", [])
    if isinstance(tracks, dict):  # a chart with one track comes back as an object, not a list
        tracks = [tracks]
    result = []
    for rank, track in enumerate(tracks, start=1):
        artist = track.get("artist")
        result.append({
            "rank": rank,
            "name": track.get("name", ""),
            "artist": artist.get("name", "") if isinstance(artist, dict) else str(artist or ""),
            "url": track.get("url"),
            "playcount": to_int(track.get("playcount")),
            "listeners": to_int(track.get("listeners")),
        })
    return result


# ---------------------------------------------------------------- the database
SCHEMA = """
CREATE TABLE IF NOT EXISTS artists (
    id   INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS tracks (
    id        INTEGER PRIMARY KEY,
    artist_id INTEGER NOT NULL REFERENCES artists(id),
    name      TEXT NOT NULL,
    url       TEXT,
    UNIQUE (artist_id, name)
);
-- One row per track, per chart, per day.
CREATE TABLE IF NOT EXISTS chart_snapshots (
    snapshot_date TEXT    NOT NULL,   -- YYYY-MM-DD
    chart         TEXT    NOT NULL,   -- 'global' or a country name
    track_id      INTEGER NOT NULL REFERENCES tracks(id),
    rank          INTEGER NOT NULL,
    playcount     INTEGER,
    listeners     INTEGER,
    PRIMARY KEY (snapshot_date, chart, track_id)
);
-- One row per artist we have already looked up. filename is empty when no photo was found,
-- so we do not ask Deezer about the same artist every day.
CREATE TABLE IF NOT EXISTS artist_images (
    artist_id INTEGER PRIMARY KEY REFERENCES artists(id),
    filename  TEXT
);
"""


def open_database():
    db = sqlite3.connect(DB_FILE)
    db.executescript(SCHEMA)  # creates the tables the first time, does nothing after that
    return db


def save_snapshot(db, day, chart, tracks):
    """Store one chart for one day. Running it twice on the same day just overwrites."""
    with db:  # commits when finished
        for t in tracks:
            db.execute("INSERT OR IGNORE INTO artists (name) VALUES (?)", (t["artist"],))
            artist_id = db.execute("SELECT id FROM artists WHERE name = ?", (t["artist"],)).fetchone()[0]
            db.execute("INSERT OR IGNORE INTO tracks (artist_id, name, url) VALUES (?, ?, ?)",
                       (artist_id, t["name"], t["url"]))
            track_id = db.execute("SELECT id FROM tracks WHERE artist_id = ? AND name = ?",
                                  (artist_id, t["name"])).fetchone()[0]
            db.execute("INSERT OR REPLACE INTO chart_snapshots VALUES (?, ?, ?, ?, ?, ?)",
                       (day, chart, track_id, t["rank"], t["playcount"], t["listeners"]))


# ---------------------------------------------------------------- artist photos (Deezer)
def simplify(name):
    """'Kite & Co' and 'kite co' count as the same name."""
    return re.sub(r"[^a-z0-9]", "", name.lower())


def find_photo_url(name):
    """Return a photo address for the artist, or None. Only an exact name match is accepted,
    so we never show the wrong person."""
    data = fetch_json("https://api.deezer.com/search/artist", {"q": name, "limit": 5})
    for artist in data.get("data", []):
        if simplify(artist.get("name", "")) == simplify(name):
            url = artist.get("picture_big") or ""
            # Deezer uses an address containing "/artist//" when the artist has no picture.
            return None if not url or "/artist//" in url else url
    return None


def download(url, path):
    request = urllib.request.Request(url, headers={"User-Agent": "MusicTrends/1.0"})
    with urllib.request.urlopen(request, timeout=15) as response:
        path.write_bytes(response.read())


def fetch_missing_photos(db):
    """Look up photos for artists on the latest charts that we have not looked up yet."""
    new_artists = db.execute("""
        SELECT DISTINCT a.id, a.name
        FROM chart_snapshots s
        JOIN tracks  t ON t.id = s.track_id
        JOIN artists a ON a.id = t.artist_id
        WHERE s.snapshot_date = (SELECT MAX(snapshot_date) FROM chart_snapshots)
          AND a.id NOT IN (SELECT artist_id FROM artist_images)
    """).fetchall()
    IMG_DIR.mkdir(parents=True, exist_ok=True)
    found = missing = 0
    for artist_id, name in new_artists:
        try:
            url = find_photo_url(name)
            filename = None
            if url:
                filename = f"{artist_id}.jpg"
                download(url, IMG_DIR / filename)
        except (OSError, ValueError):
            continue  # network hiccup: not recorded, so tomorrow's run tries again
        with db:
            db.execute("INSERT OR REPLACE INTO artist_images VALUES (?, ?)", (artist_id, filename))
        found, missing = (found + 1, missing) if filename else (found, missing + 1)
        time.sleep(0.15)  # be polite to Deezer
    return found, missing


# ---------------------------------------------------------------- run everything
def main():
    api_key = read_api_key()
    if not api_key:
        print("No Last.fm API key found. Put LASTFM_API_KEY=yourkey in a file called .env")
        return 1

    try:
        charts = {"global": get_chart(api_key, "chart.getTopTracks")}
        for country in COUNTRIES:
            charts[country] = get_chart(api_key, "geo.getTopTracks", country=country)
    except (RuntimeError, OSError, ValueError) as error:
        print(f"Could not get the charts: {error}")
        return 1

    db = open_database()
    today = date.today().isoformat()
    for chart, tracks in charts.items():
        save_snapshot(db, today, chart, tracks)
        print(f"{chart}: saved {len(tracks)} tracks")

    found, missing = fetch_missing_photos(db)
    print(f"artist photos: {found} new, {missing} not found")
    db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
