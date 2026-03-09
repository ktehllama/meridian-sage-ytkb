"""
YouTube Knowledge Base — Unified Pipeline
==========================================
Replaces yt_scraper.py + vector_builder.py with a single script.
Scrapes channels, chunks transcripts, and embeds into ChromaDB — incrementally.
Adding a new channel never rebuilds existing vectors, only processes new videos.

Usage:
    python pipeline.py add-channel "@ycombinator"
    python pipeline.py add-channel "@ycombinator" --limit 10
    python pipeline.py add-channel "@ycombinator" --sort-by views --limit 50
    python pipeline.py add-channel "@levelsio" --db knowledge.db --vectors my_vectors
    python pipeline.py add-from-csv my_whitelist.txt
    python pipeline.py queue add @ycombinator --limit 200 --sort-by views
    python pipeline.py queue run
    python pipeline.py queue status
    python pipeline.py queue reset
    python pipeline.py sync                 # embed anything in SQLite not yet in Chroma
    python pipeline.py status
    python pipeline.py rebuild              # force re-embed everything
    python pipeline.py search "how to find product market fit"

Defaults:
    --db      knowledge.db
    --vectors yc_vectors

Requirements (install once):
    pip install youtube-transcript-api yt-dlp chromadb

"""

import re
import sqlite3
import json
import time
import random
import argparse
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

# Ensure emoji and Unicode output works on Windows terminals
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import requests
import yt_dlp
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import NoTranscriptFound, TranscriptsDisabled

try:
    import chromadb
except ImportError:
    print("❌  chromadb not installed. Run: pip install chromadb")
    sys.exit(1)


# -----------------------------------------
# USER-AGENT POOL
# -----------------------------------------

_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
]


# -----------------------------------------
# DEFAULTS
# -----------------------------------------

DEFAULT_DB      = "knowledge.db"
DEFAULT_VECTORS = "yc_vectors"
COLLECTION_NAME      = "transcripts"
META_COLLECTION_NAME = "video_metadata"
CHUNK_WORDS     = 150
OVERLAP_WORDS   = 50
SCRAPE_DELAY    = 1.0   # seconds between transcript fetches

# Video filtering defaults
DEFAULT_MIN_DURATION  = 300          # 5 minutes — kills shorts
DEFAULT_MAX_DURATION  = 7200         # 2 hours — kills livestreams
DEFAULT_SKIP_KEYWORDS = ['shorts']   # title keywords that auto-skip


# -----------------------------------------
# RATE-LIMIT DETECTION
# -----------------------------------------

class RateLimitError(Exception):
    """Raised when YouTube rate-limits / IP-blocks a request."""


_RATE_LIMIT_SIGNALS = ["429", "too many requests", "blocked", "ratelimit", "rate limit"]


def _is_rate_limit(exc: Exception) -> bool:
    msg = str(exc).lower()
    return any(sig in msg for sig in _RATE_LIMIT_SIGNALS)


# -----------------------------------------
# CHANNEL STATS (for run receipts)
# -----------------------------------------

@dataclass
class ChannelStats:
    channel: str
    videos_attempted: int = 0
    videos_success:   int = 0
    videos_no_trans:  int = 0
    videos_skipped:   int = 0   # already in DB
    chunks_added:     int = 0
    elapsed_sec:    float = 0.0
    paused_at_video:  int = None   # video index when rate-limited
    error:            str = None
    status:           str = "done"  # done | paused | failed


# ==========================================
# LAYER 1: SQLITE
# ==========================================

def init_db(db_path: str) -> sqlite3.Connection:
    """Create or open the SQLite DB and ensure schema exists."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.executescript("""
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

        CREATE TABLE IF NOT EXISTS channel_queue (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            channel          TEXT NOT NULL,
            limit_count      INTEGER,
            sort_by          TEXT DEFAULT 'date',
            min_duration     INTEGER DEFAULT 300,
            max_duration     INTEGER DEFAULT 7200,
            skip_keywords    TEXT,
            whitelist_csv    TEXT,
            status           TEXT DEFAULT 'pending',
            queued_at        TEXT NOT NULL,
            started_at       TEXT,
            finished_at      TEXT,
            error_msg        TEXT,
            videos_scraped   INTEGER DEFAULT 0,
            videos_success   INTEGER DEFAULT 0,
            videos_no_trans  INTEGER DEFAULT 0,
            chunks_added     INTEGER DEFAULT 0
        );

        CREATE INDEX IF NOT EXISTS idx_transcripts_video      ON transcripts(video_id);
        CREATE INDEX IF NOT EXISTS idx_videos_channel          ON videos(channel_handle);
        CREATE INDEX IF NOT EXISTS idx_videos_has_transcript   ON videos(has_transcript);
        CREATE INDEX IF NOT EXISTS idx_queue_status            ON channel_queue(status);
    """)
    conn.commit()
    return conn


def fetch_video_list(channel: str, limit: int = None, sort_by: str = "date") -> list:
    """Use yt-dlp to get video metadata from a channel.

    sort_by='date'  — returns newest first (yt-dlp default, limit applied server-side)
    sort_by='views' — fetches full list, sorts by view_count desc, then applies limit
    """
    if channel.startswith("http"):
        url = channel.rstrip("/") + "/videos"
    elif channel.startswith("@"):
        url = f"https://www.youtube.com/{channel}/videos"
    else:
        url = f"https://www.youtube.com/@{channel}/videos"

    print(f"\n📡 Fetching video list: {url}")

    opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": True,
        "skip_download": True,
        "http_headers": {"User-Agent": random.choice(_USER_AGENTS)},
    }
    # When sorting by views we need the full list first, so don't cap server-side
    if sort_by == "date" and limit:
        opts["playlistend"] = limit

    videos = []
    with yt_dlp.YoutubeDL(opts) as ydl:
        try:
            info = ydl.extract_info(url, download=False)
        except Exception as e:
            if _is_rate_limit(e):
                raise RateLimitError(e) from e
            print(f"❌ yt-dlp error: {e}")
            return []

        for entry in (info.get("entries") or []):
            if not entry or not entry.get("id"):
                continue
            videos.append({
                "id":           entry["id"],
                "title":        entry.get("title") or "Unknown",
                "description":  (entry.get("description") or "")[:2000],
                "published_at": entry.get("upload_date"),
                "duration":     entry.get("duration"),
                "view_count":   entry.get("view_count"),
                "url":          f"https://www.youtube.com/watch?v={entry['id']}",
            })

    if sort_by == "views":
        videos.sort(key=lambda v: v.get("view_count") or 0, reverse=True)
        if limit:
            videos = videos[:limit]
        print(f"   ✅ Found {len(videos)} videos (sorted by view count)")
    else:
        print(f"   ✅ Found {len(videos)} videos on channel")

    return videos


def _apply_filters(
    videos: list,
    min_duration: int = DEFAULT_MIN_DURATION,
    max_duration: int = DEFAULT_MAX_DURATION,
    skip_keywords: list = None,
) -> tuple[list, dict]:
    """
    Filter a video list by duration and title keywords.
    Returns (filtered_list, stats_dict).
    """
    if skip_keywords is None:
        skip_keywords = DEFAULT_SKIP_KEYWORDS

    skipped_short    = []
    skipped_long     = []
    skipped_keywords = []
    kept             = []

    for v in videos:
        dur   = v.get("duration") or 0
        title = (v.get("title") or "").lower()

        # Keyword check
        matched_kw = next((kw for kw in skip_keywords if kw.lower() in title), None)
        if matched_kw:
            skipped_keywords.append(v)
            continue

        # Duration checks (skip if duration is 0/None — probably a live stream)
        if dur == 0 or dur < min_duration:
            skipped_short.append(v)
            continue

        if max_duration and dur > max_duration:
            skipped_long.append(v)
            continue

        kept.append(v)

    stats = {
        "kept":             len(kept),
        "skipped_short":    len(skipped_short),
        "skipped_long":     len(skipped_long),
        "skipped_keywords": len(skipped_keywords),
    }
    return kept, stats


def _parse_whitelist_csv(path: str) -> set[str]:
    """Parse a whitelist file: one URL or bare video ID per line.

    Supported formats per line:
      https://www.youtube.com/watch?v=VIDEO_ID
      https://youtu.be/VIDEO_ID
      VIDEO_ID   (11-character alphanumeric)
    Lines starting with # and blank lines are ignored.
    """
    ids = set()
    _url_re = re.compile(r'(?:v=|youtu\.be/)([A-Za-z0-9_-]{11})')
    _id_re  = re.compile(r'^[A-Za-z0-9_-]{11}$')

    with open(path, "r", encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            m = _url_re.search(line)
            if m:
                ids.add(m.group(1))
            elif _id_re.match(line):
                ids.add(line)
            else:
                print(f"   ⚠️  Whitelist line {lineno} skipped (unrecognized): {line!r}")

    return ids


_CHAT_PATTERN = re.compile(r'\b[a-z][a-z0-9_]{2,}: [A-Za-z]')


def _is_twitch_chat(text: str) -> bool:
    """Return True if transcript looks like Twitch chat.

    Twitch usernames are lowercase (e.g. 'georgehotz: hi'). Speaker labels in
    proper multi-speaker transcripts are UPPERCASE (e.g. 'HECTOR: ...'), so we
    only match all-lowercase username patterns to avoid false positives.
    """
    if not text or len(text) < 200:
        return False
    sample  = text[:2000]
    matches = len(_CHAT_PATTERN.findall(sample))
    return (matches / len(sample) * 1000) > 8  # >8 matches per 1000 chars


def fetch_transcript(video_id: str) -> dict | None:
    """Fetch transcript for a single video using youtube-transcript-api v1.x.

    Returns dict on success, None if no transcript available.
    Raises RateLimitError if YouTube is blocking requests.
    """
    try:
        session = requests.Session()
        session.headers.update({"User-Agent": random.choice(_USER_AGENTS)})
        api = YouTubeTranscriptApi(http_client=session)
        transcript_list = api.list(video_id)
        transcript = None

        for lang in ["en", "en-US", "en-GB"]:
            try:
                transcript = transcript_list.find_manually_created_transcript([lang])
                break
            except Exception:
                pass

        if not transcript:
            try:
                transcript = transcript_list.find_generated_transcript(["en", "en-US", "en-GB"])
            except Exception:
                pass

        if not transcript:
            all_langs = [t.language_code for t in transcript_list]
            try:
                transcript = transcript_list.find_transcript(all_langs)
            except Exception:
                pass

        if not transcript:
            return None

        fetched = transcript.fetch()
        segments, texts = [], []
        for s in fetched:
            segments.append({"text": s.text, "start": round(s.start, 2), "duration": round(s.duration, 2)})
            texts.append(s.text)

        full_text = " ".join(texts).replace("\n", " ").strip()

        if _is_twitch_chat(full_text):
            print(f"      ⚠️  Rejected: Twitch chat transcript detected")
            return None

        return {
            "full_text":    full_text,
            "segments":     json.dumps(segments),
            "language":     transcript.language_code,
            "is_generated": 1 if transcript.is_generated else 0,
        }

    except (NoTranscriptFound, TranscriptsDisabled):
        return None
    except Exception as e:
        if _is_rate_limit(e):
            raise RateLimitError(e) from e
        print(f"      ⚠️  Transcript error: {e}")
        return None


def scrape_channel_to_db(
    channel: str,
    conn: sqlite3.Connection,
    limit: int = None,
    min_duration: int = DEFAULT_MIN_DURATION,
    max_duration: int = DEFAULT_MAX_DURATION,
    skip_keywords: list = None,
    delay: float = SCRAPE_DELAY,
    sort_by: str = "date",
    whitelist: set[str] | None = None,
) -> tuple[list[str], ChannelStats]:
    """
    Scrape a channel into SQLite. Skips videos already in the DB.

    Returns (video_ids_with_transcripts, ChannelStats).
    On rate-limit, returns partial results with stats.status='paused'.
    """
    stats   = ChannelStats(channel=channel)
    t_start = time.time()
    cur     = conn.cursor()
    now     = datetime.now(timezone.utc).isoformat()

    cur.execute(
        "INSERT OR REPLACE INTO channels (handle, url, scraped_at) VALUES (?, ?, ?)",
        (channel, f"https://www.youtube.com/{channel}", now)
    )
    conn.commit()

    # Fetch video list — rate limit here means we return immediately
    try:
        videos = fetch_video_list(channel, limit=limit, sort_by=sort_by)
    except RateLimitError as e:
        print(f"   ⛔ Rate limit on video list fetch.")
        stats.status = "paused"
        stats.paused_at_video = 0
        stats.elapsed_sec = time.time() - t_start
        return [], stats

    if not videos:
        print("❌ No videos found.")
        stats.elapsed_sec = time.time() - t_start
        return [], stats

    # Whitelist filter (before duration/keyword filters)
    if whitelist:
        before = len(videos)
        videos = [v for v in videos if v["id"] in whitelist]
        print(f"   📋 Whitelist: {len(videos)}/{before} videos matched")

    # Duration / keyword filters
    videos, fstats = _apply_filters(videos, min_duration, max_duration, skip_keywords)
    print(f"   🎬 After filters:       {fstats['kept']} kept")
    if fstats['skipped_short']:    print(f"   ⏩ Too short (<{min_duration//60}min):  {fstats['skipped_short']}")
    if fstats['skipped_long']:     print(f"   ⏩ Too long  (>{max_duration//60}min): {fstats['skipped_long']}")
    if fstats['skipped_keywords']: print(f"   ⏩ Keyword skip:       {fstats['skipped_keywords']}")

    already_done  = {r[0] for r in cur.execute("SELECT id FROM videos WHERE has_transcript = 1")}
    already_tried = {r[0] for r in cur.execute("SELECT id FROM videos WHERE has_transcript = 0")}
    new_videos    = [v for v in videos if v["id"] not in already_done and v["id"] not in already_tried]

    skipped_ok   = len([v for v in videos if v["id"] in already_done])
    skipped_fail = len([v for v in videos if v["id"] in already_tried])
    stats.videos_skipped = skipped_ok + skipped_fail

    print(f"\n   ✅ Already in DB:        {skipped_ok}")
    print(f"   ⏭️  No transcript (prev): {skipped_fail}")
    print(f"   🆕 New to scrape:         {len(new_videos)}\n")

    for i, video in enumerate(new_videos, 1):
        vid_id = video["id"]
        print(f"   [{i}/{len(new_videos)}] {video['title'][:70]}")
        stats.videos_attempted += 1

        cur.execute("""
            INSERT OR IGNORE INTO videos
                (id, channel_handle, title, description, published_at, duration, view_count, url, scraped_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (vid_id, channel, video["title"], video["description"],
              video["published_at"], video["duration"], video["view_count"], video["url"], now))

        try:
            result = fetch_transcript(vid_id)
        except RateLimitError:
            print(f"      ⛔ Rate limit detected — pausing.")
            stats.status = "paused"
            stats.paused_at_video = i
            stats.elapsed_sec = time.time() - t_start
            conn.commit()
            return [r[0] for r in cur.execute("SELECT id FROM videos WHERE has_transcript = 1")], stats

        if result:
            cur.execute("""
                INSERT OR REPLACE INTO transcripts (video_id, full_text, segments, language, is_generated, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (vid_id, result["full_text"], result["segments"],
                  result["language"], result["is_generated"], now))
            cur.execute("UPDATE videos SET has_transcript = 1 WHERE id = ?", (vid_id,))
            wc   = len(result["full_text"].split())
            kind = "auto" if result["is_generated"] else "manual"
            print(f"         ✅ {wc:,} words [{result['language']} / {kind}]")
            stats.videos_success += 1
        else:
            cur.execute("UPDATE videos SET has_transcript = 0 WHERE id = ?", (vid_id,))
            print(f"         ⚠️  No transcript")
            stats.videos_no_trans += 1

        conn.commit()
        if i < len(new_videos):
            time.sleep(delay + random.uniform(0, max(delay, 1.0)))

    total_in_db = cur.execute("SELECT COUNT(*) FROM videos WHERE has_transcript=1").fetchone()[0]
    print(f"\n   Scraping done: {stats.videos_success} new ✅  {stats.videos_no_trans} skipped ⚠️  — {total_in_db} total in DB")

    stats.elapsed_sec = time.time() - t_start
    return [r[0] for r in cur.execute("SELECT id FROM videos WHERE has_transcript = 1")], stats


# ==========================================
# LAYER 2: CHROMA
# ==========================================

def _chunk_transcript(segments: list, target_words=CHUNK_WORDS, overlap_words=OVERLAP_WORDS) -> list:
    """Smart chunking that respects timestamp boundaries."""
    if not segments:
        return []

    chunks = []
    current_texts, current_word_count = [], 0
    chunk_start_time = segments[0]["start"]

    for i, seg in enumerate(segments):
        text = seg["text"].strip()
        if not text:
            continue

        current_texts.append(text)
        current_word_count += len(text.split())

        if current_word_count >= target_words:
            chunk_end_time = seg["start"] + seg.get("duration", 0)
            chunks.append({
                "text":       " ".join(current_texts),
                "start_time": chunk_start_time,
                "end_time":   chunk_end_time,
                "word_count": len(" ".join(current_texts).split()),
            })

            # Overlap: keep last N words
            overlap_texts, overlap_count, overlap_start = [], 0, chunk_end_time
            for j in range(len(current_texts) - 1, -1, -1):
                sw = len(current_texts[j].split())
                if overlap_count + sw > overlap_words:
                    break
                overlap_texts.insert(0, current_texts[j])
                overlap_count += sw
                si = i - (len(current_texts) - 1 - j)
                if si >= 0:
                    overlap_start = segments[si]["start"]

            current_texts      = overlap_texts
            current_word_count = overlap_count
            chunk_start_time   = overlap_start

    if current_texts:
        last = segments[-1]
        chunks.append({
            "text":       " ".join(current_texts),
            "start_time": chunk_start_time,
            "end_time":   last["start"] + last.get("duration", 0),
            "word_count": len(" ".join(current_texts).split()),
        })

    return chunks


def _fmt_ts(s: float) -> str:
    s = int(s)
    h, r = divmod(s, 3600)
    m, s = divmod(r, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _fmt_elapsed(seconds: float) -> str:
    """Format elapsed seconds as Xh Xm Xs, Xm Xs, or Xs."""
    s = int(seconds)
    h, r = divmod(s, 3600)
    m, s = divmod(r, 60)
    if h:
        return f"{h}h {m:02d}m {s:02d}s"
    elif m:
        return f"{m}m {s:02d}s"
    return f"{s}s"


def _yt_url(video_id: str, t: float) -> str:
    return f"https://www.youtube.com/watch?v={video_id}&t={int(t)}s"


def _get_or_create_collection(vectors_path: str) -> tuple:
    """Return (chroma_client, collection). Creates collection if it doesn't exist."""
    client     = chromadb.PersistentClient(path=vectors_path)
    try:
        collection = client.get_collection(name=COLLECTION_NAME)
    except Exception:
        collection = client.create_collection(
            name=COLLECTION_NAME,
            metadata={"description": "YouTube transcript chunks"}
        )
    return client, collection


def _get_or_create_meta_collection(client) -> object:
    """Return video_metadata collection (one doc per video). Creates if needed."""
    try:
        return client.get_collection(name=META_COLLECTION_NAME)
    except Exception:
        return client.create_collection(
            name=META_COLLECTION_NAME,
            metadata={"description": "YouTube video-level metadata for result boosting"}
        )


def _get_embedded_video_ids(collection) -> set[str]:
    """Return set of video_ids that already have at least one chunk in Chroma.
    Slow (O(n_chunks)) — prefer _get_embedded_video_ids_fast when meta_collection is available.
    """
    count = collection.count()
    if count == 0:
        return set()

    video_ids = set()
    batch = 10_000
    for offset in range(0, count, batch):
        data = collection.get(limit=batch, offset=offset, include=["metadatas"])
        for m in data["metadatas"]:
            if "video_id" in m:
                video_ids.add(m["video_id"])
    return video_ids


def _get_embedded_video_ids_fast(meta_collection) -> set[str]:
    """Return set of video_ids from the video_metadata collection (one doc per video).
    ~50x faster than scanning all chunks — use this instead of _get_embedded_video_ids.
    """
    count = meta_collection.count()
    if count == 0:
        return set()

    video_ids = set()
    batch = 5_000
    for offset in range(0, count, batch):
        data = meta_collection.get(limit=batch, offset=offset, include=["metadatas"])
        for m in data["metadatas"]:
            vid = m.get("video_id")
            if vid:
                video_ids.add(vid)
    return video_ids


def embed_new_videos(
    conn: sqlite3.Connection,
    vectors_path: str,
    video_ids_to_embed: list[str] | None = None,
    force_rebuild: bool = False,
) -> tuple[int, int]:
    """
    Embed videos into ChromaDB — incrementally by default.

    Returns (n_videos_embedded, n_chunks_added).
    """
    Path(vectors_path).mkdir(parents=True, exist_ok=True)
    client, collection = _get_or_create_collection(vectors_path)
    meta_collection    = _get_or_create_meta_collection(client)

    if force_rebuild:
        print("\n   ♻️  Force rebuild — clearing existing vectors...")
        client.delete_collection(COLLECTION_NAME)
        try:
            client.delete_collection(META_COLLECTION_NAME)
        except Exception:
            pass
        collection = client.create_collection(
            name=COLLECTION_NAME,
            metadata={"description": "YouTube transcript chunks"}
        )
        meta_collection = client.create_collection(
            name=META_COLLECTION_NAME,
            metadata={"description": "YouTube video-level metadata for result boosting"}
        )
        already_embedded = set()
    else:
        already_embedded = _get_embedded_video_ids_fast(meta_collection)

    # Figure out which videos to embed
    if video_ids_to_embed is not None:
        candidates = set(video_ids_to_embed)
    else:
        candidates = {
            r[0] for r in conn.execute("SELECT id FROM videos WHERE has_transcript = 1")
        }

    to_embed = candidates - already_embedded

    if not to_embed:
        print(f"\n   ✨ All {len(candidates)} videos already embedded — nothing to do.")
        return 0, 0

    print(f"\n   📦 Already embedded: {len(already_embedded)} videos")
    print(f"   🆕 New to embed:     {len(to_embed)} videos\n")

    # Fetch rows for videos we need to embed
    placeholders = ",".join("?" * len(to_embed))
    rows = conn.execute(f"""
        SELECT v.id AS video_id, v.title, v.url, v.channel_handle,
               v.duration, v.published_at, v.description, t.segments
        FROM transcripts t
        JOIN videos v ON t.video_id = v.id
        WHERE v.id IN ({placeholders}) AND t.segments IS NOT NULL
    """, list(to_embed)).fetchall()

    # Channel name lookup
    channels = {r["handle"]: r["handle"] for r in conn.execute("SELECT handle FROM channels")}

    all_docs, all_metas, all_ids = [], [], []
    meta_docs, meta_metas, meta_ids = [], [], []
    total_new_chunks = 0

    for row in rows:
        video_id     = row["video_id"]
        title        = row["title"]
        description  = row["description"] or ""
        segments     = json.loads(row["segments"])
        channel_name = channels.get(row["channel_handle"], row["channel_handle"] or "Unknown")
        video_url    = row["url"] or f"https://www.youtube.com/watch?v={video_id}"

        chunks            = _chunk_transcript(segments)
        total_new_chunks += len(chunks)

        print(f"   📹 {title[:60]}")
        print(f"      → {len(chunks)} chunks")

        for idx, chunk in enumerate(chunks):
            all_docs.append(f"{title}\n\n{chunk['text']}")
            all_metas.append({
                "video_id":          video_id,
                "video_title":       title,
                "video_url":         video_url,
                "channel_name":      channel_name,
                "start_time":        chunk["start_time"],
                "end_time":          chunk["end_time"],
                "timestamp_display": f"{_fmt_ts(chunk['start_time'])} → {_fmt_ts(chunk['end_time'])}",
                "timestamp_url":     _yt_url(video_id, chunk["start_time"]),
                "chunk_index":       idx,
                "total_chunks":      len(chunks),
                "word_count":        chunk["word_count"],
                "published_at":      row["published_at"] or "",
                "duration":          row["duration"] or 0,
            })
            all_ids.append(f"{video_id}_chunk_{idx:04d}")

        # Video-level metadata doc (one per video)
        meta_docs.append(f"{title}\n\n{description}")
        meta_metas.append({
            "video_id":    video_id,
            "video_title": title,
            "video_url":   video_url,
            "channel_name": channel_name,
            "chunk_count": len(chunks),
        })
        meta_ids.append(f"meta_{video_id}")

    if not all_docs:
        print("   ⚠️  No segments found for the target videos.")
        return 0, 0

    print(f"\n   ⏳ Embedding {total_new_chunks} chunks... ", end="", flush=True)
    t0 = time.time()

    batch_size = 100
    for i in range(0, len(all_docs), batch_size):
        end = min(i + batch_size, len(all_docs))
        collection.add(
            documents=all_docs[i:end],
            metadatas=all_metas[i:end],
            ids=all_ids[i:end],
        )
        if len(all_docs) > batch_size:
            print(f"{end}/{len(all_docs)}... ", end="", flush=True)

    print(f"done! ({time.time() - t0:.1f}s)")

    # Write video-level metadata docs
    for i in range(0, len(meta_docs), batch_size):
        end = min(i + batch_size, len(meta_docs))
        meta_collection.add(
            documents=meta_docs[i:end],
            metadatas=meta_metas[i:end],
            ids=meta_ids[i:end],
        )
    print(f"   📎 {len(meta_docs)} video-level metadata docs written")

    return len(rows), total_new_chunks


# ==========================================
# RUN RECEIPT
# ==========================================

def _print_receipt(stats_list: list[ChannelStats], total_elapsed: float):
    """Print a formatted summary receipt at the end of any scraping run."""
    sep = "=" * 62
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    print(f"\n{sep}")
    print(f"  SCRAPING RECEIPT — {now_str}")
    print(f"  Total time: {_fmt_elapsed(total_elapsed)}")
    print(f"{sep}")

    if not stats_list:
        print("  No channels processed.")
        print(f"{sep}\n")
        return

    print(f"\n  CHANNEL RESULTS")
    print(f"  {'-'*58}")

    for s in stats_list:
        icon = {"done": "✅", "paused": "⛔", "failed": "❌"}.get(s.status, "?")
        row = (
            f"  {icon}  {s.channel:<22}"
            f"  {s.videos_attempted:>4} scraped"
            f"  |  {s.videos_success:>3}✅ {s.videos_no_trans:>3}⚠️"
            f"  |  {s.chunks_added:>6,} chunks"
            f"  |  {_fmt_elapsed(s.elapsed_sec)}"
        )
        print(row)
        if s.status == "paused" and s.paused_at_video:
            print(f"       -> Rate limit at video {s.paused_at_video}")
        elif s.status == "failed" and s.error:
            print(f"       -> Error: {s.error[:80]}")

    n_done   = sum(1 for s in stats_list if s.status == "done")
    n_paused = sum(1 for s in stats_list if s.status == "paused")
    n_failed = sum(1 for s in stats_list if s.status == "failed")
    total_attempted = sum(s.videos_attempted for s in stats_list)
    total_success   = sum(s.videos_success   for s in stats_list)
    total_no_trans  = sum(s.videos_no_trans  for s in stats_list)
    total_chunks    = sum(s.chunks_added     for s in stats_list)
    pct = (total_no_trans / total_attempted * 100) if total_attempted else 0

    print(f"\n  TOTALS")
    print(f"  {'-'*58}")
    print(f"  Channels:     {len(stats_list)} total  |  ✅ {n_done} done  ⛔ {n_paused} paused  ❌ {n_failed} failed")
    print(f"  New videos:   {total_attempted} scraped  |  {total_chunks:,} chunks added")
    if total_attempted:
        print(f"  No transcript: {total_no_trans} ({pct:.1f}%)")
    print(f"  Elapsed:      {_fmt_elapsed(total_elapsed)}")

    if n_paused:
        print(f"\n{sep}")
        print(f"  ⚠️  Queue paused (rate limit). Change IP then run:")
        print(f"      python pipeline.py queue reset")
        print(f"      python pipeline.py queue run")

    print(f"{sep}\n")


# ==========================================
# TOP-LEVEL PIPELINE COMMANDS
# ==========================================

def cmd_add_channel(
    channel: str,
    db_path: str,
    vectors_path: str,
    limit: int = None,
    min_duration: int = DEFAULT_MIN_DURATION,
    max_duration: int = DEFAULT_MAX_DURATION,
    skip_keywords: list = None,
    delay: float = SCRAPE_DELAY,
    sort_by: str = "date",
    whitelist_path: str = None,
):
    """Full pipeline: scrape channel → embed new videos."""
    sep = "=" * 60
    print(f"\n{sep}")
    print(f"  ADD CHANNEL: {channel}")
    print(f"  DB:      {db_path}")
    print(f"  Vectors: {vectors_path}/")
    kw_str   = ", ".join(skip_keywords or DEFAULT_SKIP_KEYWORDS)
    sort_str = "by view count" if sort_by == "views" else "newest first"
    print(f"  Filters: >{min_duration//60}min / <{max_duration//60}min / skip: [{kw_str}]")
    print(f"  Sort:    {sort_str}")
    if whitelist_path:
        print(f"  Whitelist: {whitelist_path}")
    print(f"{sep}")

    t_start  = time.time()
    conn     = init_db(db_path)
    whitelist = None
    if whitelist_path:
        whitelist = _parse_whitelist_csv(whitelist_path)
        print(f"   📋 Loaded {len(whitelist)} IDs from whitelist")

    # Step 1: Scrape
    print(f"\n{'-'*60}")
    print("  STEP 1 / 2 — Scraping transcripts")
    print(f"{'-'*60}")
    scraped_ids, ch_stats = scrape_channel_to_db(
        channel, conn,
        limit=limit, min_duration=min_duration, max_duration=max_duration,
        skip_keywords=skip_keywords, delay=delay,
        sort_by=sort_by, whitelist=whitelist,
    )

    # Step 2: Embed (only new videos)
    print(f"\n{'-'*60}")
    print("  STEP 2 / 2 — Embedding into vector DB")
    print(f"{'-'*60}")
    new_vids, new_chunks = embed_new_videos(conn, vectors_path, video_ids_to_embed=scraped_ids)
    ch_stats.chunks_added = new_chunks

    client2, collection = _get_or_create_collection(vectors_path)
    meta_col2     = _get_or_create_meta_collection(client2)
    total_chunks  = collection.count()
    embedded_vids = len(_get_embedded_video_ids_fast(meta_col2))

    print(f"\n{sep}")
    status_icon = "⛔ PAUSED" if ch_stats.status == "paused" else "✅  DONE"
    print(f"  {status_icon} — {channel}")
    print(f"  Newly embedded:    {new_vids} video(s) / {new_chunks:,} chunks")
    print(f"  Total in vectors:  {embedded_vids} videos / {total_chunks:,} chunks")
    print(f"{sep}\n")

    conn.close()
    _print_receipt([ch_stats], time.time() - t_start)


def cmd_add_from_csv(
    csv_path: str,
    db_path: str,
    vectors_path: str,
    min_duration: int = DEFAULT_MIN_DURATION,
    max_duration: int = DEFAULT_MAX_DURATION,
    skip_keywords: list = None,
    delay: float = SCRAPE_DELAY,
):
    """Scrape specific videos from a whitelist file (URLs or video IDs, one per line)."""
    if not Path(csv_path).exists():
        print(f"❌  File not found: {csv_path}")
        sys.exit(1)

    video_ids = _parse_whitelist_csv(csv_path)
    if not video_ids:
        print("❌  No valid video IDs found in file.")
        sys.exit(1)

    sep = "=" * 60
    print(f"\n{sep}")
    print(f"  ADD FROM CSV: {csv_path}")
    print(f"  {len(video_ids)} video IDs to process")
    print(f"  DB:      {db_path}")
    print(f"  Vectors: {vectors_path}/")
    print(f"{sep}")

    t_start     = time.time()
    conn        = init_db(db_path)
    now         = datetime.now(timezone.utc).isoformat()
    stats       = ChannelStats(channel=csv_path)
    scraped_ids = []

    for i, vid_id in enumerate(sorted(video_ids), 1):
        print(f"\n   [{i}/{len(video_ids)}] {vid_id}")
        stats.videos_attempted += 1

        # Fetch video metadata via yt-dlp
        try:
            with yt_dlp.YoutubeDL({
                "quiet": True, "no_warnings": True, "skip_download": True,
                "http_headers": {"User-Agent": random.choice(_USER_AGENTS)},
            }) as ydl:
                info = ydl.extract_info(f"https://www.youtube.com/watch?v={vid_id}", download=False)
        except Exception as e:
            if _is_rate_limit(e):
                print(f"   ⛔ Rate limit — stopping.")
                stats.status = "paused"
                stats.paused_at_video = i
                break
            print(f"   ⚠️  Metadata fetch failed: {e}")
            stats.videos_no_trans += 1
            continue

        title       = info.get("title") or "Unknown"
        duration    = info.get("duration") or 0
        description = (info.get("description") or "")[:2000]
        view_count  = info.get("view_count")
        channel_h   = info.get("uploader_id") or info.get("channel_id") or "unknown"
        video_url   = f"https://www.youtube.com/watch?v={vid_id}"
        published   = info.get("upload_date")

        print(f"      📹 {title[:60]}")

        # Apply duration/keyword filter
        filtered, _ = _apply_filters(
            [{"id": vid_id, "title": title, "duration": duration}],
            min_duration, max_duration, skip_keywords,
        )
        if not filtered:
            print(f"      ⏩ Filtered out (duration={duration}s)")
            stats.videos_no_trans += 1
            continue

        conn.execute("""
            INSERT OR IGNORE INTO videos
                (id, channel_handle, title, description, published_at, duration, view_count, url, scraped_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (vid_id, channel_h, title, description, published, duration, view_count, video_url, now))

        try:
            result = fetch_transcript(vid_id)
        except RateLimitError:
            print(f"      ⛔ Rate limit — stopping.")
            stats.status = "paused"
            stats.paused_at_video = i
            conn.commit()
            break

        if result:
            conn.execute("""
                INSERT OR REPLACE INTO transcripts (video_id, full_text, segments, language, is_generated, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (vid_id, result["full_text"], result["segments"],
                  result["language"], result["is_generated"], now))
            conn.execute("UPDATE videos SET has_transcript = 1 WHERE id = ?", (vid_id,))
            wc   = len(result["full_text"].split())
            kind = "auto" if result["is_generated"] else "manual"
            print(f"      ✅ {wc:,} words [{result['language']} / {kind}]")
            stats.videos_success += 1
            scraped_ids.append(vid_id)
        else:
            conn.execute("UPDATE videos SET has_transcript = 0 WHERE id = ?", (vid_id,))
            print(f"      ⚠️  No transcript")
            stats.videos_no_trans += 1

        conn.commit()
        if i < len(video_ids):
            time.sleep(delay + random.uniform(0, max(delay, 1.0)))

    print(f"\n   Scraping done: {stats.videos_success} ✅  {stats.videos_no_trans} ⚠️")

    if scraped_ids:
        print(f"\n{'-'*60}")
        print("  Embedding into vector DB")
        print(f"{'-'*60}")
        n_vids, n_chunks = embed_new_videos(conn, vectors_path, video_ids_to_embed=scraped_ids)
        stats.chunks_added = n_chunks

    conn.close()
    stats.elapsed_sec = time.time() - t_start
    _print_receipt([stats], stats.elapsed_sec)


# -----------------------------------------
# QUEUE COMMANDS
# -----------------------------------------

def cmd_queue_add(
    channel: str,
    db_path: str,
    limit: int = None,
    sort_by: str = "date",
    min_duration: int = DEFAULT_MIN_DURATION,
    max_duration: int = DEFAULT_MAX_DURATION,
    skip_keywords: list = None,
    whitelist_csv: str = None,
):
    """Add a channel to the scraping queue."""
    conn    = init_db(db_path)
    now     = datetime.now(timezone.utc).isoformat()
    kw_str  = ",".join(skip_keywords) if skip_keywords else None
    conn.execute("""
        INSERT INTO channel_queue
            (channel, limit_count, sort_by, min_duration, max_duration, skip_keywords, whitelist_csv, queued_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (channel, limit, sort_by, min_duration, max_duration, kw_str, whitelist_csv, now))
    conn.commit()
    pending = conn.execute("SELECT COUNT(*) FROM channel_queue WHERE status='pending'").fetchone()[0]
    limit_str = f"--limit {limit}" if limit else "no limit"
    print(f"   ✅ Queued {channel}  [{limit_str} | sort:{sort_by}]  ({pending} total pending)")
    conn.close()


def cmd_queue_status(db_path: str):
    """Show all entries in the channel queue."""
    conn = init_db(db_path)
    rows = conn.execute("SELECT * FROM channel_queue ORDER BY id").fetchall()

    sep = "=" * 72
    print(f"\n{sep}")
    print(f"  CHANNEL QUEUE: {db_path}")
    print(f"{sep}")

    if not rows:
        print("  Queue is empty.  Add with: pipeline.py queue add @channel")
        print(f"{sep}\n")
        conn.close()
        return

    icons = {"pending": "⏳", "done": "✅", "paused": "⛔", "failed": "❌", "running": "🔄"}
    print(f"  {'#':>3}  {'CHANNEL':<24}  {'STATUS':<9}  {'LIMIT':>6}  {'SORT':<6}  RESULT")
    print(f"  {'-'*68}")

    for r in rows:
        limit_str = str(r["limit_count"]) if r["limit_count"] else "all"
        icon = icons.get(r["status"], "?")
        result = ""
        if r["status"] == "done":
            result = f"{r['videos_success']}✅ {r['videos_no_trans']}⚠️  {r['chunks_added']:,}ch"
        elif r["status"] in ("paused", "failed") and r["error_msg"]:
            result = r["error_msg"][:35]
        print(f"  {r['id']:>3}  {r['channel']:<24}  {icon} {r['status']:<8}  {limit_str:>6}  {r['sort_by']:<6}  {result}")

    counts = {}
    for r in rows:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    summary = "  ".join(
        f"{icons.get(s,'?')} {n} {s}" for s, n in counts.items()
    )
    print(f"\n  {len(rows)} entries: {summary}")
    print(f"{sep}\n")
    conn.close()


def cmd_queue_reset(db_path: str, channel: str = None):
    """Reset paused/failed channels back to pending."""
    conn = init_db(db_path)
    if channel:
        n = conn.execute(
            "UPDATE channel_queue SET status='pending', error_msg=NULL WHERE channel=? AND status IN ('paused','failed','running')",
            (channel,)
        ).rowcount
        msg = f"for {channel}"
    else:
        n = conn.execute(
            "UPDATE channel_queue SET status='pending', error_msg=NULL WHERE status IN ('paused','failed','running')"
        ).rowcount
        msg = "(all paused/failed/interrupted)"
    conn.commit()
    if n:
        print(f"   ✅ Reset {n} entr{'y' if n==1 else 'ies'} {msg} → pending")
        print(f"   Run: python pipeline.py queue run")
    else:
        print(f"   Nothing to reset {msg}.")
    conn.close()


def cmd_queue_remove(db_path: str, channel: str = None, queue_id: int = None, status: str = None):
    """Remove entries from the channel queue."""
    conn = init_db(db_path)

    if queue_id is not None:
        row = conn.execute("SELECT channel, status FROM channel_queue WHERE id=?", (queue_id,)).fetchone()
        if not row:
            print(f"   ❌  No queue entry with id={queue_id}.")
            conn.close()
            return
        conn.execute("DELETE FROM channel_queue WHERE id=?", (queue_id,))
        conn.commit()
        print(f"   🗑️  Removed queue entry #{queue_id} ({row['channel']}, was {row['status']})")

    elif channel:
        rows = conn.execute("SELECT id, status FROM channel_queue WHERE channel=?", (channel,)).fetchall()
        if not rows:
            print(f"   ❌  No queue entries found for '{channel}'.")
            conn.close()
            return
        conn.execute("DELETE FROM channel_queue WHERE channel=?", (channel,))
        conn.commit()
        print(f"   🗑️  Removed {len(rows)} entr{'y' if len(rows)==1 else 'ies'} for {channel}")

    elif status:
        n = conn.execute("DELETE FROM channel_queue WHERE status=?", (status,)).rowcount
        conn.commit()
        if n:
            print(f"   🗑️  Removed {n} entr{'y' if n==1 else 'ies'} with status='{status}'")
        else:
            print(f"   Nothing to remove with status='{status}'.")

    else:
        print("   ❌  Specify a channel, --id, or --status to remove entries.")
        print("   Examples:")
        print("     python pipeline.py queue remove @ycombinator")
        print("     python pipeline.py queue remove --id 3")
        print("     python pipeline.py queue remove --status done")

    conn.close()


def cmd_queue_run(db_path: str, vectors_path: str, delay: float = SCRAPE_DELAY, scrape_only: bool = False, embed_on_ban: bool = False):
    """Process all pending channels in the queue."""
    conn = init_db(db_path)
    rows = conn.execute(
        "SELECT * FROM channel_queue WHERE status='pending' ORDER BY id"
    ).fetchall()

    if not rows:
        total = conn.execute("SELECT COUNT(*) FROM channel_queue").fetchone()[0]
        if total == 0:
            print("   Queue is empty.  Add with: pipeline.py queue add @channel")
        else:
            paused = conn.execute("SELECT COUNT(*) FROM channel_queue WHERE status='paused'").fetchone()[0]
            failed = conn.execute("SELECT COUNT(*) FROM channel_queue WHERE status='failed'").fetchone()[0]
            print(f"   No pending channels.  (paused: {paused}, failed: {failed})")
            if paused or failed:
                print(f"   Run `pipeline.py queue reset` to retry them.")
        conn.close()
        return

    sep = "=" * 60
    print(f"\n{sep}")
    print(f"  QUEUE RUN — {len(rows)} channel(s) pending")
    if scrape_only:
        print(f"  Mode:    SCRAPE ONLY (no embedding — run `sync` afterward)")
    print(f"  DB:      {db_path}")
    print(f"  Vectors: {vectors_path}/")
    print(f"{sep}")

    t_run_start = time.time()
    stats_list  = []

    for idx, row in enumerate(rows, 1):
        channel = row["channel"]

        print(f"\n{'-'*60}")
        print(f"  [{idx}/{len(rows)}] {channel}")
        print(f"{'-'*60}")

        now_iso = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "UPDATE channel_queue SET status='running', started_at=? WHERE id=?",
            (now_iso, row["id"])
        )
        conn.commit()

        kw        = [k.strip() for k in row["skip_keywords"].split(",")] if row["skip_keywords"] else None
        whitelist = _parse_whitelist_csv(row["whitelist_csv"]) if row["whitelist_csv"] else None

        try:
            step_label = "STEP 1 / 1" if scrape_only else "STEP 1 / 2"
            print(f"\n  {step_label} — Scraping transcripts")
            scraped_ids, ch_stats = scrape_channel_to_db(
                channel, conn,
                limit=row["limit_count"],
                min_duration=row["min_duration"],
                max_duration=row["max_duration"],
                skip_keywords=kw,
                delay=delay,
                sort_by=row["sort_by"],
                whitelist=whitelist,
            )

            if scrape_only:
                ch_stats.chunks_added = 0
            else:
                print(f"\n  STEP 2 / 2 — Embedding into vector DB")
                n_vids, n_chunks = embed_new_videos(conn, vectors_path, video_ids_to_embed=scraped_ids)
                ch_stats.chunks_added = n_chunks

            finished = datetime.now(timezone.utc).isoformat()
            if ch_stats.status == "paused":
                conn.execute("""
                    UPDATE channel_queue
                    SET status='paused', finished_at=?, error_msg=?,
                        videos_scraped=?, videos_success=?, videos_no_trans=?, chunks_added=?
                    WHERE id=?
                """, (finished,
                      f"Rate limit at video {ch_stats.paused_at_video}",
                      ch_stats.videos_attempted, ch_stats.videos_success,
                      ch_stats.videos_no_trans, ch_stats.chunks_added,
                      row["id"]))
                conn.commit()
                stats_list.append(ch_stats)
                print(f"\n   ⛔ Stopping queue due to rate limit on {channel}.")
                if embed_on_ban:
                    print(f"\n   --embed-on-ban set — starting embed of all scraped transcripts...")
                    conn.close()
                    embed_new_videos(init_db(db_path), vectors_path)
                    conn = init_db(db_path)
                    print(f"   Embedding complete.")
                break
            else:
                conn.execute("""
                    UPDATE channel_queue
                    SET status='done', finished_at=?,
                        videos_scraped=?, videos_success=?, videos_no_trans=?, chunks_added=?
                    WHERE id=?
                """, (finished,
                      ch_stats.videos_attempted, ch_stats.videos_success,
                      ch_stats.videos_no_trans, ch_stats.chunks_added,
                      row["id"]))
                conn.commit()
                stats_list.append(ch_stats)

        except Exception as e:
            err_msg = str(e)[:200]
            print(f"\n   ❌ Unexpected error: {err_msg}")
            conn.execute("""
                UPDATE channel_queue SET status='failed', finished_at=?, error_msg=? WHERE id=?
            """, (datetime.now(timezone.utc).isoformat(), err_msg, row["id"]))
            conn.commit()
            failed_stats = ChannelStats(
                channel=channel,
                elapsed_sec=ch_stats.elapsed_sec if "ch_stats" in dir() else 0.0,
                error=err_msg,
                status="failed",
            )
            stats_list.append(failed_stats)
            # Non-rate-limit errors: continue to next channel

    conn.close()
    _print_receipt(stats_list, time.time() - t_run_start)


def cmd_status(db_path: str, vectors_path: str):
    """Show current state of both the SQLite DB and vector DB."""
    sep = "=" * 60
    print(f"\n{sep}")
    print("  KNOWLEDGE BASE STATUS")
    print(f"{sep}")

    # SQLite stats
    if Path(db_path).exists():
        conn = sqlite3.connect(db_path)
        channels  = [r[0] for r in conn.execute("SELECT handle FROM channels")]
        total_v   = conn.execute("SELECT COUNT(*) FROM videos").fetchone()[0]
        with_t    = conn.execute("SELECT COUNT(*) FROM videos WHERE has_transcript=1").fetchone()[0]
        without_t = conn.execute("SELECT COUNT(*) FROM videos WHERE has_transcript=0").fetchone()[0]
        words     = conn.execute(
            "SELECT SUM(LENGTH(full_text)-LENGTH(REPLACE(full_text,' ',''))+1) FROM transcripts"
        ).fetchone()[0] or 0

        # Queue stats
        q_rows = conn.execute("SELECT status, COUNT(*) FROM channel_queue GROUP BY status").fetchall()
        q_counts = {r[0]: r[1] for r in q_rows}
        conn.close()

        print(f"\n  📄 SQLite DB: {db_path}")
        print(f"     Channels:       {', '.join(channels) or 'none'}")
        print(f"     Videos total:   {total_v}")
        print(f"     With transcripts: {with_t}")
        print(f"     No transcript:  {without_t}")
        print(f"     Total words:    ~{words:,}")

        if q_counts:
            q_str = "  ".join(f"{s}: {n}" for s, n in q_counts.items())
            print(f"     Queue:          {q_str}")
    else:
        print(f"\n  📄 SQLite DB: {db_path}  (not found)")

    # Chroma stats
    if Path(vectors_path).exists():
        client, collection = _get_or_create_collection(vectors_path)
        meta_collection    = _get_or_create_meta_collection(client)
        total_chunks       = collection.count()
        embedded_ids       = _get_embedded_video_ids_fast(meta_collection)

        # Channel names: read from SQLite (instant) rather than scanning all ChromaDB chunks
        if Path(db_path).exists():
            _conn = sqlite3.connect(db_path)
            channels_in_vec = [r[0] for r in _conn.execute("SELECT handle FROM channels ORDER BY handle")]
            _conn.close()
        else:
            # Fallback: sample first 500 chunks (fast, may miss some channels)
            channels_in_vec = set()
            if total_chunks > 0:
                sample = collection.get(limit=500, offset=0, include=["metadatas"])
                for m in sample["metadatas"]:
                    ch = m.get("channel_name", "")
                    if ch:
                        channels_in_vec.add(ch)
            channels_in_vec = sorted(channels_in_vec)

        print(f"\n  🗂️  Vector DB:  {vectors_path}/")
        print(f"     Channels:   {', '.join(channels_in_vec) or 'none'}")
        print(f"     Videos:     {len(embedded_ids)}")
        print(f"     Chunks:     {total_chunks:,}")
    else:
        print(f"\n  🗂️  Vector DB:  {vectors_path}/  (not found — run add-channel first)")

    print(f"\n{sep}\n")


def cmd_rebuild(db_path: str, vectors_path: str):
    """Force re-embed all videos (wipes and rebuilds the vector DB)."""
    if not Path(db_path).exists():
        print(f"❌  DB not found: {db_path}")
        sys.exit(1)

    print(f"\n⚠️  This will wipe and rebuild all vectors in: {vectors_path}/")
    confirm = input("   Continue? [y/N] ").strip().lower()
    if confirm != "y":
        print("   Cancelled.")
        return

    conn = init_db(db_path)
    embed_new_videos(conn, vectors_path, force_rebuild=True)
    conn.close()

    _, collection = _get_or_create_collection(vectors_path)
    print(f"\n✅  Rebuild complete — {collection.count():,} chunks in {vectors_path}/")


def cmd_rechunk(db_path: str, vectors_path: str):
    """Wipe and re-embed everything with the current chunk size (no re-scraping)."""
    if not Path(db_path).exists():
        print(f"❌  DB not found: {db_path}")
        sys.exit(1)

    sep = "=" * 60
    print(f"\n{sep}")
    print(f"  RECHUNK — re-embed all videos at {CHUNK_WORDS}-word chunks")
    print(f"  DB:      {db_path}")
    print(f"  Vectors: {vectors_path}/")
    print(f"{sep}")

    conn = init_db(db_path)
    embed_new_videos(conn, vectors_path, force_rebuild=True)
    conn.close()

    _, collection = _get_or_create_collection(vectors_path)
    print(f"\n✅  Rechunk complete — {collection.count():,} chunks in {vectors_path}/\n")


def cmd_sync(db_path: str, vectors_path: str):
    """Embed any videos in SQLite that are missing from ChromaDB."""
    sep = "=" * 60
    print(f"\n{sep}")
    print("  SYNC — SQLite → Vector DB")
    print(f"  DB:      {db_path}")
    print(f"  Vectors: {vectors_path}/")
    print(f"{sep}")

    if not Path(db_path).exists():
        print(f"\n❌  DB not found: {db_path}")
        sys.exit(1)

    conn = init_db(db_path)

    sqlite_ids          = {r[0] for r in conn.execute("SELECT id FROM videos WHERE has_transcript = 1")}
    sync_client, collection = _get_or_create_collection(vectors_path)
    sync_meta_col       = _get_or_create_meta_collection(sync_client)
    embedded_ids        = _get_embedded_video_ids_fast(sync_meta_col)
    missing       = sqlite_ids - embedded_ids

    print(f"\n  📄 SQLite transcripts:  {len(sqlite_ids)}")
    print(f"  🗂️  Chroma embedded:     {len(embedded_ids)}")
    print(f"  🔀 Missing from Chroma: {len(missing)}")

    if not missing:
        print("\n  ✨ Already in sync — nothing to do.")
        conn.close()
        return

    print(f"\n{'-'*60}")
    new_vids, new_chunks = embed_new_videos(conn, vectors_path)
    conn.close()

    _, collection = _get_or_create_collection(vectors_path)
    print(f"\n{sep}")
    print(f"  ✅  SYNC COMPLETE")
    print(f"  Newly embedded: {new_vids} video(s) / {new_chunks:,} chunks")
    print(f"  Total chunks:   {collection.count():,}")
    print(f"{sep}\n")


def cmd_search(query: str, vectors_path: str, top_n: int = 5):
    """Quick semantic search from the CLI."""
    if not Path(vectors_path).exists():
        print(f"❌  Vector DB not found: {vectors_path}")
        sys.exit(1)

    _, collection = _get_or_create_collection(vectors_path)
    print(f'\n🔍 "{query}"\n')

    results = collection.query(
        query_texts=[query],
        n_results=top_n,
        include=["documents", "metadatas", "distances"]
    )

    if not results["documents"][0]:
        print("  No results found.")
        return

    for i, (doc, meta, dist) in enumerate(zip(
        results["documents"][0], results["metadatas"][0], results["distances"][0]
    )):
        score   = max(0, 1 - dist / 2)
        preview = doc.split("\n\n", 1)[1] if "\n\n" in doc else doc
        if len(preview) > 350:
            preview = preview[:350] + "..."

        print(f"  {'-'*56}")
        print(f"  #{i+1} ({score:.0%}) — {meta['video_title']}")
        print(f"  ⏱  {meta['timestamp_display']}  🔗 {meta['timestamp_url']}")
        print(f"\n  {preview}\n")

    print(f"  {'-'*56}")


# ==========================================
# FIX-CHANNEL-IDS
# ==========================================

def cmd_fix_channel_ids(db_path: str, vectors_path: str):
    """Re-fetch metadata for videos stored with raw UC... channel IDs and update to @handles."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    rows = conn.execute(
        "SELECT id, url, channel_handle FROM videos WHERE channel_handle LIKE 'UC%'"
    ).fetchall()

    if not rows:
        print("No UC... channel IDs found. Nothing to fix.")
        conn.close()
        return

    print(f"Found {len(rows)} video(s) with UC... channel IDs. Re-fetching metadata...")

    client     = chromadb.PersistentClient(path=vectors_path)
    collection = client.get_collection(name=COLLECTION_NAME)

    ydl_opts = {"quiet": True, "skip_download": True, "no_warnings": True}
    fixed, failed = 0, 0

    for row in rows:
        vid_id    = row["id"]
        old_handle = row["channel_handle"]
        video_url  = row["url"] or f"https://www.youtube.com/watch?v={vid_id}"

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(video_url, download=False)
            new_handle = info.get("uploader_id") or info.get("channel_id") or old_handle

            if new_handle == old_handle:
                print(f"  ⚠️  {vid_id}: uploader_id still {old_handle} — skipping")
                continue

            # Update SQLite
            conn.execute("UPDATE videos SET channel_handle=? WHERE id=?", (new_handle, vid_id))
            conn.commit()

            # Update ChromaDB: delete existing chunks, re-add with corrected channel_name
            existing = collection.get(where={"video_id": vid_id}, include=["documents", "metadatas"])
            if existing["ids"]:
                collection.delete(ids=existing["ids"])

                updated_metas = []
                for meta in existing["metadatas"]:
                    m = dict(meta)
                    m["channel_name"] = new_handle
                    updated_metas.append(m)

                collection.add(
                    ids=existing["ids"],
                    documents=existing["documents"],
                    metadatas=updated_metas,
                )
                print(f"  ✅  {vid_id}: {old_handle} → {new_handle} ({len(existing['ids'])} chunks updated)")
            else:
                print(f"  ✅  {vid_id}: {old_handle} → {new_handle} (no chunks in vector DB)")

            fixed += 1
        except Exception as e:
            print(f"  ❌  {vid_id}: {e}")
            failed += 1

    conn.close()
    print(f"\nDone. Fixed: {fixed} | Failed: {failed}")


# ==========================================
# CLI
# ==========================================

def main():
    parser = argparse.ArgumentParser(
        description="YouTube Knowledge Base — Unified Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Commands:
  add-channel   Scrape a channel and embed new videos into the vector DB
  add-from-csv  Scrape specific videos from a whitelist file (URLs or IDs)
  queue add     Add a channel to the scraping queue
  queue run     Process all pending channels in the queue
  queue status  Show queue state
  queue reset   Reset paused/failed channels back to pending
  sync          Embed any videos in SQLite not yet in ChromaDB
  status        Show DB and vector DB stats
  rebuild       Wipe and re-embed everything
  rechunk       Wipe and re-embed with current chunk size (no re-scraping)
  search        Quick semantic search from the terminal

Examples:
  python pipeline.py add-channel "@ycombinator"
  python pipeline.py add-channel "@ycombinator" --limit 100 --sort-by views
  python pipeline.py add-channel "@ycombinator" --whitelist my_videos.txt
  python pipeline.py add-from-csv my_videos.txt
  python pipeline.py queue add @ycombinator --limit 200 --sort-by views
  python pipeline.py queue add @levelsio
  python pipeline.py queue run
  python pipeline.py queue status
  python pipeline.py queue reset
  python pipeline.py sync
  python pipeline.py status
  python pipeline.py search "how to validate a startup idea"
        """
    )

    parser.add_argument("--db",      default=DEFAULT_DB,      help=f"SQLite DB path (default: {DEFAULT_DB})")
    parser.add_argument("--vectors", default=DEFAULT_VECTORS, help=f"ChromaDB path (default: {DEFAULT_VECTORS})")

    sub = parser.add_subparsers(dest="command")

    # -- add-channel ------------------------------------------
    ac = sub.add_parser("add-channel", help="Scrape a channel and embed into vector DB")
    ac.add_argument("channel")
    ac.add_argument("--limit",         type=int,   help="Max videos to scrape")
    ac.add_argument("--delay",         type=float, default=SCRAPE_DELAY,        help="Delay between requests (default: 1.0s)")
    ac.add_argument("--min-duration",  type=int,   default=DEFAULT_MIN_DURATION, dest="min_duration")
    ac.add_argument("--max-duration",  type=int,   default=DEFAULT_MAX_DURATION, dest="max_duration")
    ac.add_argument("--skip-keywords", type=str,   default=None,                 dest="skip_keywords")
    ac.add_argument("--sort-by",       type=str,   default="date", choices=["date", "views"], dest="sort_by",
                    help="Sort order: 'date' (newest first) or 'views' (most viewed first)")
    ac.add_argument("--whitelist",     type=str,   default=None,
                    help="Path to a whitelist file (URLs/IDs, one per line)")

    # -- add-from-csv -----------------------------------------
    afc = sub.add_parser("add-from-csv", help="Scrape specific videos from a whitelist file")
    afc.add_argument("csv_path", help="Path to file with one YouTube URL or video ID per line")
    afc.add_argument("--delay",         type=float, default=SCRAPE_DELAY,        help="Delay between requests")
    afc.add_argument("--min-duration",  type=int,   default=DEFAULT_MIN_DURATION, dest="min_duration")
    afc.add_argument("--max-duration",  type=int,   default=DEFAULT_MAX_DURATION, dest="max_duration")
    afc.add_argument("--skip-keywords", type=str,   default=None,                 dest="skip_keywords")

    # -- queue ------------------------------------------------
    queue_p  = sub.add_parser("queue", help="Manage the scraping queue")
    queue_sub = queue_p.add_subparsers(dest="queue_cmd")

    # queue add
    qa = queue_sub.add_parser("add", help="Add a channel to the queue")
    qa.add_argument("channel")
    qa.add_argument("--limit",         type=int,   help="Max videos to scrape")
    qa.add_argument("--sort-by",       type=str,   default="date", choices=["date", "views"], dest="sort_by")
    qa.add_argument("--min-duration",  type=int,   default=DEFAULT_MIN_DURATION, dest="min_duration")
    qa.add_argument("--max-duration",  type=int,   default=DEFAULT_MAX_DURATION, dest="max_duration")
    qa.add_argument("--skip-keywords", type=str,   default=None,                 dest="skip_keywords")
    qa.add_argument("--whitelist",     type=str,   default=None,
                    help="Path to a whitelist file (URLs/IDs)")

    # queue run
    qr = queue_sub.add_parser("run", help="Process all pending channels")
    qr.add_argument("--delay",       type=float, default=SCRAPE_DELAY, help="Delay between requests")
    qr.add_argument("--scrape-only", action="store_true", dest="scrape_only",
                    help="Skip embedding — only fetch transcripts into SQLite. Run `sync` afterward to embed.")
    qr.add_argument("--embed-on-ban", action="store_true", dest="embed_on_ban",
                    help="Used with --scrape-only: if an IP ban stops scraping, automatically embed everything scraped so far before exiting.")

    # queue status
    queue_sub.add_parser("status", help="Show queue state")

    # queue reset
    qreset = queue_sub.add_parser("reset", help="Reset paused/failed entries to pending")
    qreset.add_argument("channel", nargs="?", default=None, help="Specific channel to reset (omit for all)")

    # queue remove
    qremove = queue_sub.add_parser("remove", help="Delete entries from the queue")
    qremove.add_argument("channel", nargs="?", default=None, help="Channel handle to remove")
    qremove.add_argument("--id",     type=int,  default=None, dest="queue_id", help="Remove by queue ID")
    qremove.add_argument("--status", type=str,  default=None, help="Remove all entries with this status (e.g. done)")

    # -- sync / status / rebuild / rechunk / search / fix-channel-ids --------
    sub.add_parser("sync",             help="Embed videos in SQLite missing from ChromaDB")
    sub.add_parser("status",           help="Show current state of DB and vector DB")
    sub.add_parser("rebuild",          help="Wipe and re-embed all videos")
    sub.add_parser("rechunk",          help=f"Wipe and re-embed at current chunk size ({CHUNK_WORDS} words)")
    sub.add_parser("fix-channel-ids",  help="Re-fetch metadata for UC... channel IDs and update to @handles")

    sr = sub.add_parser("search", help="Semantic search from the CLI")
    sr.add_argument("query")
    sr.add_argument("--top", type=int, default=5)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    # -- dispatch ---------------------------------------------

    if args.command == "add-channel":
        skip_kw = [k.strip() for k in args.skip_keywords.split(",")] if args.skip_keywords else None
        cmd_add_channel(
            args.channel, args.db, args.vectors,
            limit=args.limit, min_duration=args.min_duration, max_duration=args.max_duration,
            skip_keywords=skip_kw, delay=args.delay,
            sort_by=args.sort_by, whitelist_path=args.whitelist,
        )

    elif args.command == "add-from-csv":
        skip_kw = [k.strip() for k in args.skip_keywords.split(",")] if args.skip_keywords else None
        cmd_add_from_csv(
            args.csv_path, args.db, args.vectors,
            min_duration=args.min_duration, max_duration=args.max_duration,
            skip_keywords=skip_kw, delay=args.delay,
        )

    elif args.command == "queue":
        if not args.queue_cmd:
            queue_p.print_help()
            sys.exit(0)

        if args.queue_cmd == "add":
            skip_kw = [k.strip() for k in args.skip_keywords.split(",")] if args.skip_keywords else None
            cmd_queue_add(
                args.channel, args.db,
                limit=args.limit, sort_by=args.sort_by,
                min_duration=args.min_duration, max_duration=args.max_duration,
                skip_keywords=skip_kw, whitelist_csv=args.whitelist,
            )
        elif args.queue_cmd == "run":
            cmd_queue_run(args.db, args.vectors, delay=args.delay, scrape_only=args.scrape_only, embed_on_ban=args.embed_on_ban)
        elif args.queue_cmd == "status":
            cmd_queue_status(args.db)
        elif args.queue_cmd == "reset":
            cmd_queue_reset(args.db, channel=args.channel)
        elif args.queue_cmd == "remove":
            cmd_queue_remove(args.db, channel=args.channel, queue_id=args.queue_id, status=args.status)

    elif args.command == "fix-channel-ids":
        cmd_fix_channel_ids(args.db, args.vectors)
    elif args.command == "sync":
        cmd_sync(args.db, args.vectors)
    elif args.command == "status":
        cmd_status(args.db, args.vectors)
    elif args.command == "rebuild":
        cmd_rebuild(args.db, args.vectors)
    elif args.command == "rechunk":
        cmd_rechunk(args.db, args.vectors)
    elif args.command == "search":
        cmd_search(args.query, args.vectors, top_n=args.top)


if __name__ == "__main__":
    main()
