"""
YouTube Knowledge Base — Unified Pipeline
==========================================
Replaces yt_scraper.py + vector_builder.py with a single script.
Scrapes channels, chunks transcripts, and embeds into ChromaDB — incrementally.
Adding a new channel never rebuilds existing vectors, only processes new videos.

Usage:
    python pipeline.py add-channel "@ycombinator"
    python pipeline.py add-channel "@ycombinator" --limit 10
    python pipeline.py add-channel "@ycombinator"
    python pipeline.py add-channel "@levelsio" --db knowledge.db --vectors my_vectors
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

import sqlite3
import json
import time
import random
import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests
import yt_dlp
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import NoTranscriptFound, TranscriptsDisabled

try:
    import chromadb
except ImportError:
    print("❌  chromadb not installed. Run: pip install chromadb")
    sys.exit(1)


# ─────────────────────────────────────────
# USER-AGENT POOL
# ─────────────────────────────────────────

_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
]


# ─────────────────────────────────────────
# DEFAULTS
# ─────────────────────────────────────────

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


# ══════════════════════════════════════════
# LAYER 1: SQLITE  (from yt_scraper.py)
# ══════════════════════════════════════════

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

        CREATE INDEX IF NOT EXISTS idx_transcripts_video ON transcripts(video_id);
        CREATE INDEX IF NOT EXISTS idx_videos_channel    ON videos(channel_handle);
    """)
    conn.commit()
    return conn


def fetch_video_list(channel: str, limit: int = None) -> list:
    """Use yt-dlp to get all video metadata from a channel."""
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
    if limit:
        opts["playlistend"] = limit

    videos = []
    with yt_dlp.YoutubeDL(opts) as ydl:
        try:
            info = ydl.extract_info(url, download=False)
        except Exception as e:
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


def fetch_transcript(video_id: str) -> dict | None:
    """Fetch transcript for a single video using youtube-transcript-api v1.x."""
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

        return {
            "full_text":    " ".join(texts).replace("\n", " ").strip(),
            "segments":     json.dumps(segments),
            "language":     transcript.language_code,
            "is_generated": 1 if transcript.is_generated else 0,
        }

    except (NoTranscriptFound, TranscriptsDisabled):
        return None
    except Exception as e:
        print(f"      ⚠️  Transcript error: {e}")
        return None


def scrape_channel_to_db(channel: str, conn: sqlite3.Connection, limit: int = None, min_duration: int = DEFAULT_MIN_DURATION, max_duration: int = DEFAULT_MAX_DURATION, skip_keywords: list = None, delay: float = SCRAPE_DELAY) -> list[str]:
    """
    Scrape a channel into SQLite. Skips videos already in the DB.
    Returns list of video_ids that now have transcripts (including pre-existing ones).
    """
    cur = conn.cursor()
    now = datetime.now(timezone.utc).isoformat()

    cur.execute(
        "INSERT OR REPLACE INTO channels (handle, url, scraped_at) VALUES (?, ?, ?)",
        (channel, f"https://www.youtube.com/{channel}", now)
    )
    conn.commit()

    videos = fetch_video_list(channel, limit=limit)
    if not videos:
        print("❌ No videos found.")
        return []

    # Apply filters
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

    print(f"\n   ✅ Already in DB:        {skipped_ok}")
    print(f"   ⏭️  No transcript (prev): {skipped_fail}")
    print(f"   🆕 New to scrape:         {len(new_videos)}\n")

    success = 0
    failed  = 0

    for i, video in enumerate(new_videos, 1):
        vid_id = video["id"]
        print(f"   [{i}/{len(new_videos)}] {video['title'][:70]}")

        cur.execute("""
            INSERT OR IGNORE INTO videos
                (id, channel_handle, title, description, published_at, duration, view_count, url, scraped_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (vid_id, channel, video["title"], video["description"],
              video["published_at"], video["duration"], video["view_count"], video["url"], now))

        result = fetch_transcript(vid_id)
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
            success += 1
        else:
            cur.execute("UPDATE videos SET has_transcript = 0 WHERE id = ?", (vid_id,))
            print(f"         ⚠️  No transcript")
            failed += 1

        conn.commit()
        if i < len(new_videos):
            time.sleep(delay + random.uniform(0, max(delay, 1.0)))

    total_in_db = cur.execute("SELECT COUNT(*) FROM videos WHERE has_transcript=1").fetchone()[0]
    print(f"\n   Scraping done: {success} new ✅  {failed} skipped ⚠️  — {total_in_db} total in DB")

    # Return all video_ids in DB that have transcripts
    return [r[0] for r in cur.execute("SELECT id FROM videos WHERE has_transcript = 1")]


# ══════════════════════════════════════════
# LAYER 2: CHROMA  (from vector_builder.py)
# ══════════════════════════════════════════

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
    """Return set of video_ids that already have at least one chunk in Chroma."""
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


def embed_new_videos(
    conn: sqlite3.Connection,
    vectors_path: str,
    video_ids_to_embed: list[str] | None = None,
    force_rebuild: bool = False,
) -> int:
    """
    Embed videos into ChromaDB — incrementally by default.

    - If force_rebuild=True: wipes the collection and re-embeds everything.
    - Otherwise: checks what's already embedded and only processes the delta.
    - If video_ids_to_embed is provided, only those IDs are candidates.

    Returns the number of newly embedded videos.
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
        already_embedded = _get_embedded_video_ids(collection)

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
        return 0

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
    total_chunks = 0

    for row in rows:
        video_id     = row["video_id"]
        title        = row["title"]
        description  = row["description"] or ""
        segments     = json.loads(row["segments"])
        channel_name = channels.get(row["channel_handle"], row["channel_handle"] or "Unknown")
        video_url    = row["url"] or f"https://www.youtube.com/watch?v={video_id}"

        chunks       = _chunk_transcript(segments)
        total_chunks += len(chunks)

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
        return 0

    print(f"\n   ⏳ Embedding {total_chunks} chunks... ", end="", flush=True)
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

    return len(rows)


# ══════════════════════════════════════════
# TOP-LEVEL PIPELINE COMMANDS
# ══════════════════════════════════════════

def cmd_add_channel(channel: str, db_path: str, vectors_path: str, limit: int = None, min_duration: int = DEFAULT_MIN_DURATION, max_duration: int = DEFAULT_MAX_DURATION, skip_keywords: list = None, delay: float = SCRAPE_DELAY):
    """Full pipeline: scrape channel → embed new videos."""
    sep = "=" * 60
    print(f"\n{sep}")
    print(f"  ADD CHANNEL: {channel}")
    print(f"  DB:      {db_path}")
    print(f"  Vectors: {vectors_path}/")
    kw_str = ", ".join(skip_keywords or DEFAULT_SKIP_KEYWORDS)
    print(f"  Filters: >{min_duration//60}min / <{max_duration//60}min / skip: [{kw_str}]")
    print(f"{sep}")

    conn = init_db(db_path)

    # Step 1: Scrape
    print(f"\n{'─'*60}")
    print("  STEP 1 / 2 — Scraping transcripts")
    print(f"{'─'*60}")
    scraped_ids = scrape_channel_to_db(channel, conn, limit=limit, min_duration=min_duration, max_duration=max_duration, skip_keywords=skip_keywords, delay=delay)

    # Step 2: Embed (only new videos)
    print(f"\n{'─'*60}")
    print("  STEP 2 / 2 — Embedding into vector DB")
    print(f"{'─'*60}")
    new_count = embed_new_videos(conn, vectors_path, video_ids_to_embed=scraped_ids)

    # Summary
    _, collection = _get_or_create_collection(vectors_path)
    total_chunks  = collection.count()
    embedded_vids = len(_get_embedded_video_ids(collection))

    print(f"\n{sep}")
    print(f"  ✅  DONE — {channel}")
    print(f"  Newly embedded:    {new_count} video(s)")
    print(f"  Total in vectors:  {embedded_vids} videos / {total_chunks:,} chunks")
    print(f"{sep}\n")

    conn.close()


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
        conn.close()

        print(f"\n  📄 SQLite DB: {db_path}")
        print(f"     Channels:       {', '.join(channels) or 'none'}")
        print(f"     Videos total:   {total_v}")
        print(f"     With transcripts: {with_t}")
        print(f"     No transcript:  {without_t}")
        print(f"     Total words:    ~{words:,}")
    else:
        print(f"\n  📄 SQLite DB: {db_path}  (not found)")

    # Chroma stats
    if Path(vectors_path).exists():
        _, collection   = _get_or_create_collection(vectors_path)
        total_chunks    = collection.count()
        embedded_ids    = _get_embedded_video_ids(collection)

        channels_in_vec = set()
        if total_chunks > 0:
            batch = 10_000
            for offset in range(0, total_chunks, batch):
                data = collection.get(limit=batch, offset=offset, include=["metadatas"])
                for m in data["metadatas"]:
                    ch = m.get("channel_name", "")
                    if ch:
                        channels_in_vec.add(ch)

        print(f"\n  🗂️  Vector DB:  {vectors_path}/")
        print(f"     Channels:   {', '.join(sorted(channels_in_vec)) or 'none'}")
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

    # Show the gap before syncing
    sqlite_ids = {r[0] for r in conn.execute("SELECT id FROM videos WHERE has_transcript = 1")}
    _, collection = _get_or_create_collection(vectors_path)
    embedded_ids  = _get_embedded_video_ids(collection)
    missing       = sqlite_ids - embedded_ids

    print(f"\n  📄 SQLite transcripts:  {len(sqlite_ids)}")
    print(f"  🗂️  Chroma embedded:     {len(embedded_ids)}")
    print(f"  🔀 Missing from Chroma: {len(missing)}")

    if not missing:
        print("\n  ✨ Already in sync — nothing to do.")
        conn.close()
        return

    print(f"\n{'─'*60}")
    new_count = embed_new_videos(conn, vectors_path)
    conn.close()

    _, collection = _get_or_create_collection(vectors_path)
    print(f"\n{sep}")
    print(f"  ✅  SYNC COMPLETE")
    print(f"  Newly embedded: {new_count} video(s)")
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

        print(f"  {'─'*56}")
        print(f"  #{i+1} ({score:.0%}) — {meta['video_title']}")
        print(f"  ⏱  {meta['timestamp_display']}  🔗 {meta['timestamp_url']}")
        print(f"\n  {preview}\n")

    print(f"  {'─'*56}")


# ══════════════════════════════════════════
# CLI
# ══════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="YouTube Knowledge Base — Unified Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Commands:
  add-channel   Scrape a channel and embed new videos into the vector DB
  sync          Embed any videos in SQLite not yet in ChromaDB (use after IP blocks)
  status        Show DB and vector DB stats
  rebuild       Wipe and re-embed everything (use if vectors get out of sync)
  rechunk       Wipe and re-embed with current chunk size (no re-scraping)
  search        Quick semantic search from the terminal

Examples:
  python pipeline.py add-channel "@ycombinator"
  python pipeline.py add-channel "@ycombinator" --limit 100
  python pipeline.py add-channel "@ycombinator" --min-duration 600 --max-duration 7200
  python pipeline.py add-channel "@ycombinator" --skip-keywords "shorts,clip,trailer"
  python pipeline.py add-channel "@levelsio" --db kb.db --vectors kb_vectors
  python pipeline.py sync
  python pipeline.py status
  python pipeline.py rebuild
  python pipeline.py rechunk
  python pipeline.py search "how to validate a startup idea"
        """
    )

    parser.add_argument("--db",      default=DEFAULT_DB,      help=f"SQLite DB path (default: {DEFAULT_DB})")
    parser.add_argument("--vectors", default=DEFAULT_VECTORS, help=f"ChromaDB path (default: {DEFAULT_VECTORS})")

    sub = parser.add_subparsers(dest="command")

    # add-channel
    ac = sub.add_parser("add-channel", help="Scrape a channel and embed into vector DB")
    ac.add_argument("channel", help="Channel handle e.g. @ycombinator or full URL")
    ac.add_argument("--limit",   type=int,   help="Max videos to scrape (useful for testing)")
    ac.add_argument("--delay",        type=float, default=SCRAPE_DELAY,         help="Delay between requests (default: 1.0s)")
    ac.add_argument("--min-duration",  type=int,   default=DEFAULT_MIN_DURATION,  dest="min_duration",  help="Min video duration in seconds (default: 300 = 5min)")
    ac.add_argument("--max-duration",  type=int,   default=DEFAULT_MAX_DURATION,  dest="max_duration",  help="Max video duration in seconds (default: 14400 = 4hr)")
    ac.add_argument("--skip-keywords", type=str,   default=None,                  dest="skip_keywords", help='Comma-separated title keywords to skip (default: "shorts")')

    # sync
    sub.add_parser("sync", help="Embed videos in SQLite that are missing from ChromaDB")

    # status
    sub.add_parser("status", help="Show current state of DB and vector DB")

    # rebuild
    sub.add_parser("rebuild", help="Wipe and re-embed all videos")

    # rechunk
    sub.add_parser("rechunk", help=f"Wipe and re-embed at current chunk size ({CHUNK_WORDS} words) — no re-scraping")

    # search
    sr = sub.add_parser("search", help="Semantic search from the CLI")
    sr.add_argument("query", help="Natural language query")
    sr.add_argument("--top", type=int, default=5, help="Number of results (default: 5)")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    if args.command == "add-channel":
        skip_kw = [k.strip() for k in args.skip_keywords.split(",")] if args.skip_keywords else None
        cmd_add_channel(args.channel, args.db, args.vectors, limit=args.limit, min_duration=args.min_duration, max_duration=args.max_duration, skip_keywords=skip_kw, delay=args.delay)
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