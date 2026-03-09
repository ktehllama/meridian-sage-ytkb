"""
YouTube Knowledge Base Scraper - Phase 1
=========================================
Scrapes all videos + transcripts from a YouTube channel
and stores them in a SQLite database.

Requirements:
    pip install youtube-transcript-api yt-dlp

Usage:
    python yt_scraper.py scrape --channel "@ycombinator" --output yc.db --limit 5
    python yt_scraper.py scrape --channel "@ycombinator" --output yc.db
    python yt_scraper.py search --db yc.db --query "product market fit"
    python yt_scraper.py stats --db yc.db
"""

import sqlite3
import json
import time
import argparse
from datetime import datetime, timezone

import yt_dlp
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import NoTranscriptFound, TranscriptsDisabled


# ─────────────────────────────────────────
# DATABASE SETUP
# ─────────────────────────────────────────

def init_db(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.executescript("""
        CREATE TABLE IF NOT EXISTS channels (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            handle      TEXT NOT NULL UNIQUE,
            name        TEXT,
            url         TEXT,
            scraped_at  TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS videos (
            id              TEXT PRIMARY KEY,
            channel_handle  TEXT NOT NULL,
            title           TEXT,
            description     TEXT,
            published_at    TEXT,
            duration        INTEGER,
            view_count      INTEGER,
            url             TEXT,
            has_transcript  INTEGER DEFAULT 0,
            scraped_at      TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS transcripts (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            video_id     TEXT NOT NULL UNIQUE,
            full_text    TEXT NOT NULL,
            segments     TEXT,
            language     TEXT,
            is_generated INTEGER DEFAULT 1,
            created_at   TEXT NOT NULL,
            FOREIGN KEY (video_id) REFERENCES videos(id)
        );

        CREATE INDEX IF NOT EXISTS idx_transcripts_video ON transcripts(video_id);
        CREATE INDEX IF NOT EXISTS idx_videos_channel ON videos(channel_handle);
    """)
    conn.commit()
    return conn


# ─────────────────────────────────────────
# FETCH VIDEO LIST  (yt-dlp Python API)
# ─────────────────────────────────────────

def fetch_video_list(channel: str, limit: int = None) -> list:
    if channel.startswith("http"):
        channel_url = channel.rstrip("/") + "/videos"
    elif channel.startswith("@"):
        channel_url = f"https://www.youtube.com/{channel}/videos"
    else:
        channel_url = f"https://www.youtube.com/@{channel}/videos"

    print(f"\n📡 Fetching video list from: {channel_url}")

    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": True,
        "skip_download": True,
    }
    if limit:
        ydl_opts["playlistend"] = limit

    videos = []
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(channel_url, download=False)
        except Exception as e:
            print(f"❌ yt-dlp error: {e}")
            return []

        for entry in info.get("entries", []):
            if not entry or not entry.get("id"):
                continue
            videos.append({
                "id":           entry.get("id"),
                "title":        entry.get("title") or "Unknown",
                "description":  (entry.get("description") or "")[:2000],
                "published_at": entry.get("upload_date"),
                "duration":     entry.get("duration"),
                "view_count":   entry.get("view_count"),
                "url":          f"https://www.youtube.com/watch?v={entry.get('id')}",
            })

    print(f"✅ Found {len(videos)} videos")
    return videos


# ─────────────────────────────────────────
# FETCH TRANSCRIPT  (youtube-transcript-api v1.x)
# ─────────────────────────────────────────

def fetch_transcript(video_id: str):
    """
    Uses youtube-transcript-api v1.x (released Jan 2026).
    Key change: must instantiate YouTubeTranscriptApi() and call .list() / .fetch()
    as instance methods — all old static methods were removed.
    """
    try:
        api = YouTubeTranscriptApi()
        transcript_list = api.list(video_id)

        transcript = None

        # 1. Prefer manually-created English
        for lang in ["en", "en-US", "en-GB"]:
            try:
                transcript = transcript_list.find_manually_created_transcript([lang])
                break
            except Exception:
                pass

        # 2. Fall back to auto-generated English
        if not transcript:
            try:
                transcript = transcript_list.find_generated_transcript(["en", "en-US", "en-GB"])
            except Exception:
                pass

        # 3. Accept any language
        if not transcript:
            all_langs = [t.language_code for t in transcript_list]
            try:
                transcript = transcript_list.find_transcript(all_langs)
            except Exception:
                pass

        if not transcript:
            return None

        fetched = transcript.fetch()

        segments = []
        texts = []
        for snippet in fetched:
            segments.append({
                "text":     snippet.text,
                "start":    round(snippet.start, 2),
                "duration": round(snippet.duration, 2),
            })
            texts.append(snippet.text)

        full_text = " ".join(texts).replace("\n", " ").strip()

        return {
            "full_text":    full_text,
            "segments":     json.dumps(segments),
            "language":     transcript.language_code,
            "is_generated": 1 if transcript.is_generated else 0,
        }

    except (NoTranscriptFound, TranscriptsDisabled):
        return None
    except Exception as e:
        print(f"      ⚠️  Error: {e}")
        return None


# ─────────────────────────────────────────
# MAIN SCRAPER
# ─────────────────────────────────────────

def scrape_channel(channel: str, db_path: str, limit: int = None, delay: float = 1.0):
    conn = init_db(db_path)
    cur = conn.cursor()
    now = datetime.now(timezone.utc).isoformat()

    cur.execute(
        "INSERT OR REPLACE INTO channels (handle, url, scraped_at) VALUES (?, ?, ?)",
        (channel, f"https://www.youtube.com/{channel}", now)
    )
    conn.commit()

    videos = fetch_video_list(channel, limit=limit)
    if not videos:
        print("❌ No videos found. Check the channel handle and try again.")
        conn.close()
        return

    existing = {r[0] for r in cur.execute("SELECT id FROM videos WHERE has_transcript = 1")}
    tried    = {r[0] for r in cur.execute("SELECT id FROM videos WHERE has_transcript = 0")}

    new_videos = [v for v in videos if v["id"] not in existing and v["id"] not in tried]

    print(f"\n   ✅ Already scraped:      {len([v for v in videos if v['id'] in existing])}")
    print(f"   ⏭️  No transcript (prev): {len([v for v in videos if v['id'] in tried])}")
    print(f"   🆕 New to process:        {len(new_videos)}\n")

    if not new_videos:
        print("Nothing new to scrape!")
        conn.close()
        return

    success = 0
    no_transcript = 0

    for i, video in enumerate(new_videos, 1):
        vid_id = video["id"]
        print(f"[{i}/{len(new_videos)}] {video['title'][:80]}")

        cur.execute("""
            INSERT OR IGNORE INTO videos
                (id, channel_handle, title, description, published_at,
                 duration, view_count, url, scraped_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            vid_id, channel, video["title"], video["description"],
            video["published_at"], video["duration"], video["view_count"],
            video["url"], now
        ))

        result = fetch_transcript(vid_id)

        if result:
            cur.execute("""
                INSERT OR REPLACE INTO transcripts
                    (video_id, full_text, segments, language, is_generated, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (vid_id, result["full_text"], result["segments"],
                  result["language"], result["is_generated"], now))
            cur.execute("UPDATE videos SET has_transcript = 1 WHERE id = ?", (vid_id,))
            word_count = len(result["full_text"].split())
            kind = "auto" if result["is_generated"] else "manual"
            print(f"      ✅ {word_count:,} words  [{result['language']} / {kind}]")
            success += 1
        else:
            cur.execute("UPDATE videos SET has_transcript = 0 WHERE id = ?", (vid_id,))
            print(f"      ⚠️  No transcript available")
            no_transcript += 1

        conn.commit()
        if i < len(new_videos):
            time.sleep(delay)

    total_in_db = cur.execute("SELECT COUNT(*) FROM videos WHERE has_transcript=1").fetchone()[0]
    total_words = cur.execute(
        "SELECT SUM(LENGTH(full_text) - LENGTH(REPLACE(full_text,' ','')) + 1) FROM transcripts"
    ).fetchone()[0] or 0

    print(f"""
{'='*60}
✅  SCRAPING COMPLETE
{'='*60}
  Channel:        {channel}
  Database:       {db_path}
  This run:       {len(new_videos)} processed
    ✅ Success:   {success}
    ⚠️  No subs:  {no_transcript}
{'─'*60}
  DB total:       {total_in_db} videos with transcripts
  Total words:    ~{total_words:,}
{'='*60}
""")
    conn.close()


# ─────────────────────────────────────────
# SEARCH
# ─────────────────────────────────────────

def search_transcripts(db_path: str, query: str, limit: int = 5):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    rows = cur.execute("""
        SELECT
            v.title, v.url, v.published_at,
            SUBSTR(t.full_text,
                MAX(1, INSTR(LOWER(t.full_text), LOWER(?)) - 150),
                500) AS snippet
        FROM transcripts t
        JOIN videos v ON t.video_id = v.id
        WHERE LOWER(t.full_text) LIKE LOWER(?)
        LIMIT ?
    """, (query, f"%{query}%", limit)).fetchall()

    if not rows:
        print(f'\n🔍 No results for: "{query}"')
    else:
        print(f'\n🔍 Results for: "{query}"  ({len(rows)} found)\n{"="*60}')
        for r in rows:
            print(f'\n📹 {r["title"]}')
            print(f'   {r["url"]}  [{r["published_at"] or "?"}]')
            print(f'   ...{r["snippet"].strip()}...')

    conn.close()


# ─────────────────────────────────────────
# STATS
# ─────────────────────────────────────────

def show_stats(db_path: str):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    total      = cur.execute("SELECT COUNT(*) FROM videos").fetchone()[0]
    with_t     = cur.execute("SELECT COUNT(*) FROM videos WHERE has_transcript=1").fetchone()[0]
    without_t  = cur.execute("SELECT COUNT(*) FROM videos WHERE has_transcript=0").fetchone()[0]
    words      = cur.execute(
        "SELECT SUM(LENGTH(full_text)-LENGTH(REPLACE(full_text,' ',''))+1) FROM transcripts"
    ).fetchone()[0] or 0
    channels   = [r[0] for r in cur.execute("SELECT handle FROM channels")]
    avg        = (words // with_t) if with_t else 0

    print(f"""
{'='*60}
📊  KNOWLEDGE BASE STATS
{'='*60}
  Channels:          {', '.join(channels)}
  Total videos:      {total}
  With transcript:   {with_t}
  No transcript:     {without_t}
  Total words:       ~{words:,}
  Avg words/video:   ~{avg:,}
{'='*60}
""")
    conn.close()


# ─────────────────────────────────────────
# CLI
# ─────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="YouTube Channel Transcript Scraper",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python yt_scraper.py scrape --channel "@ycombinator" --output yc.db --limit 5
  python yt_scraper.py scrape --channel "@ycombinator" --output yc.db
  python yt_scraper.py search --db yc.db --query "product market fit"
  python yt_scraper.py stats  --db yc.db
        """
    )
    sub = parser.add_subparsers(dest="command")

    sp = sub.add_parser("scrape")
    sp.add_argument("--channel", required=True)
    sp.add_argument("--output", default="knowledge_base.db")
    sp.add_argument("--limit", type=int)
    sp.add_argument("--delay", type=float, default=1.0)

    se = sub.add_parser("search")
    se.add_argument("--db", required=True)
    se.add_argument("--query", required=True)
    se.add_argument("--limit", type=int, default=5)

    st = sub.add_parser("stats")
    st.add_argument("--db", required=True)

    args = parser.parse_args()

    if args.command == "scrape":
        scrape_channel(args.channel, args.output, args.limit, args.delay)
    elif args.command == "search":
        search_transcripts(args.db, args.query, args.limit)
    elif args.command == "stats":
        show_stats(args.db)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()