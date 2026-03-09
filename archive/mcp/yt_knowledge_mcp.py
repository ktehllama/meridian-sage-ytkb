"""
YouTube Knowledge Base MCP Server
===================================
Exposes your ChromaDB transcript knowledge base to Claude Desktop.
Claude can search videos, get context from specific videos, and list what's available.

Setup:
    pip install "mcp[cli]" chromadb sentence-transformers rank_bm25

    Add to your Claude Desktop config file:

    Windows: %APPDATA%\\Claude\\claude_desktop_config.json
    macOS:   ~/Library/Application Support/Claude/claude_desktop_config.json

    {
      "mcpServers": {
        "yt_knowledge": {
          "command": "python",
          "args": ["C:/full/path/to/yt_knowledge_mcp.py"],
          "env": {
            "CHROMA_DB_PATH": "C:/full/path/to/yc_vectors",
            "CHROMA_COLLECTION": "transcripts",
            "SQLITE_DB_PATH": "C:/full/path/to/knowledge.db",
            "BM25_CACHE_PATH": "C:/full/path/to/bm25_cache.pkl"
          }
        }
      }
    }

    Then restart Claude Desktop. You should see a hammer icon with the tools available.
"""

import os
import sys
import sqlite3
import logging
import threading
import pickle
from typing import Optional

from mcp.server.fastmcp import FastMCP

import chromadb
from rank_bm25 import BM25Okapi
from sentence_transformers import CrossEncoder


# ─────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────

CHROMA_DB_PATH    = os.environ.get("CHROMA_DB_PATH", "./chroma_db")
CHROMA_COLLECTION = os.environ.get("CHROMA_COLLECTION", "transcripts")
META_COLLECTION   = "video_metadata"
SQLITE_DB_PATH    = os.environ.get("SQLITE_DB_PATH", "./knowledge.db")
BM25_CACHE_PATH   = os.environ.get("BM25_CACHE_PATH", "./bm25_cache.pkl")

# stdio MCP servers must log to stderr (stdout is the protocol channel)
logging.basicConfig(stream=sys.stderr, level=logging.INFO)
logger = logging.getLogger("yt_knowledge_mcp")


# ─────────────────────────────────────────
# CHROMADB INITIALIZATION
# ─────────────────────────────────────────

_collection      = None
_meta_collection = None
_init_error      = None
_chroma_client   = None


def _get_collection():
    """Lazy-initialize ChromaDB chunk collection on first use."""
    global _collection, _meta_collection, _init_error, _chroma_client

    if _collection is not None:
        return _collection
    if _init_error is not None:
        return None

    if not os.path.exists(CHROMA_DB_PATH):
        _init_error = f"ChromaDB directory not found: {CHROMA_DB_PATH}"
        logger.error(_init_error)
        return None

    try:
        logger.info(f"Connecting to ChromaDB at: {CHROMA_DB_PATH}")
        _chroma_client = chromadb.PersistentClient(path=CHROMA_DB_PATH)
        _collection    = _chroma_client.get_collection(name=CHROMA_COLLECTION)
        count = _collection.count()
        logger.info(f"Connected! {count} chunks in '{CHROMA_COLLECTION}'")

        # Also load the video metadata collection (best-effort)
        try:
            _meta_collection = _chroma_client.get_collection(name=META_COLLECTION)
            logger.info(f"Video metadata collection loaded: {_meta_collection.count()} docs")
        except Exception:
            logger.info("No video_metadata collection found — video-level boosting disabled")

        # Start BM25 index build in background — don't block MCP startup
        threading.Thread(target=_build_bm25_background, daemon=True).start()

        return _collection
    except Exception as e:
        _init_error = f"Failed to load collection '{CHROMA_COLLECTION}': {e}"
        try:
            available = [c.name for c in _chroma_client.list_collections()]
            if available:
                _init_error += f"\nAvailable collections: {available}"
        except Exception:
            pass
        logger.error(_init_error)
        return None


# ─────────────────────────────────────────
# BM25 INDEX  (background thread + disk cache)
# ─────────────────────────────────────────

_bm25_index = None
_bm25_ids   = []   # parallel list of chunk IDs
_bm25_docs  = []   # parallel list of raw doc strings (for cross-encoder)
_bm25_ready = threading.Event()
_bm25_lock  = threading.Lock()


def _build_bm25_background():
    """Build BM25 index in background thread. Loads from disk cache if chunk count matches."""
    global _bm25_index, _bm25_ids, _bm25_docs

    if _collection is None:
        return
    count = _collection.count()
    if count == 0:
        _bm25_ready.set()
        return

    # Try loading from cache
    if os.path.exists(BM25_CACHE_PATH):
        try:
            with open(BM25_CACHE_PATH, "rb") as f:
                cached = pickle.load(f)
            if cached.get("chunk_count") == count:
                with _bm25_lock:
                    _bm25_ids   = cached["ids"]
                    _bm25_docs  = cached["docs"]
                    _bm25_index = cached["index"]
                logger.info(f"BM25 loaded from cache ({count} chunks)")
                _bm25_ready.set()
                return
        except Exception as e:
            logger.warning(f"BM25 cache load failed: {e}")

    # Build from scratch
    logger.info(f"Building BM25 index over {count} chunks (background)...")
    batch = 10_000
    all_ids, all_docs = [], []
    for offset in range(0, count, batch):
        data = _collection.get(limit=batch, offset=offset, include=["documents"])
        all_ids.extend(data["ids"])
        all_docs.extend(data["documents"])

    tokenized = [doc.lower().split() for doc in all_docs]
    index     = BM25Okapi(tokenized)

    with _bm25_lock:
        _bm25_ids   = all_ids
        _bm25_docs  = all_docs
        _bm25_index = index

    # Save cache
    try:
        with open(BM25_CACHE_PATH, "wb") as f:
            pickle.dump({"chunk_count": count, "ids": all_ids, "docs": all_docs, "index": index}, f)
        logger.info("BM25 cache saved")
    except Exception as e:
        logger.warning(f"BM25 cache save failed: {e}")

    _bm25_ready.set()
    logger.info("BM25 index ready")


# ─────────────────────────────────────────
# CROSS-ENCODER  (background thread)
# ─────────────────────────────────────────

_cross_encoder = None


def _load_cross_encoder():
    global _cross_encoder
    logger.info("Loading cross-encoder model (cross-encoder/ms-marco-MiniLM-L-6-v2)...")
    _cross_encoder = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
    logger.info("Cross-encoder ready")


threading.Thread(target=_load_cross_encoder, daemon=True).start()


# ─────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────

def _seconds_to_timestamp(seconds: float) -> str:
    """Convert seconds to MM:SS or HH:MM:SS."""
    seconds = int(seconds)
    if seconds >= 3600:
        return f"{seconds // 3600}:{(seconds % 3600) // 60:02d}:{seconds % 60:02d}"
    return f"{seconds // 60}:{seconds % 60:02d}"


def _format_chunk(doc: str, metadata: dict, score: float, index: int) -> str:
    """Format a single retrieved chunk for Claude to read."""
    title     = metadata.get("video_title", "Unknown Video")
    video_id  = metadata.get("video_id", "")
    start     = metadata.get("start_time", 0)
    end       = metadata.get("end_time", 0)
    chunk_idx = metadata.get("chunk_index", "?")
    total     = metadata.get("total_chunks", "?")

    yt_link = f"https://www.youtube.com/watch?v={video_id}&t={int(start)}s" if video_id else ""

    return (
        f"--- EXCERPT {index + 1} (Relevance: {score * 100:.1f}%) ---\n"
        f"Video: \"{title}\"\n"
        f"Timestamp: {_seconds_to_timestamp(start)} → {_seconds_to_timestamp(end)}\n"
        f"YouTube Link: {yt_link}\n"
        f"Chunk: {chunk_idx}/{total}\n\n"
        f"{doc}\n"
    )


# ─────────────────────────────────────────
# MCP SERVER
# ─────────────────────────────────────────

mcp = FastMCP("yt_knowledge_mcp")


# ─────────────────────────────────────────
# TOOLS
# ─────────────────────────────────────────

@mcp.tool()
async def yt_search_knowledge_base(query: str, n_results: int = 8) -> str:
    """Search the YouTube transcript knowledge base using semantic similarity.

    Takes a natural language question and returns the most relevant transcript
    excerpts from all indexed videos. Each excerpt includes the video title,
    timestamp, and a direct YouTube link to that exact moment.

    Use this to answer questions about topics covered in the video library.
    Synthesize the excerpts into a clear answer and cite video titles + timestamps.

    Args:
        query: Natural language search query (e.g. 'How to find product-market fit')
        n_results: Number of chunks to retrieve, 1-20. Default 8. More = broader, fewer = focused.
    """
    collection = _get_collection()
    if collection is None:
        return f"Error: {_init_error}\n\nCheck CHROMA_DB_PATH in your MCP server config."

    n_results   = max(1, min(n_results, 20))
    n_candidates = max(30, n_results * 4)

    # ── Step 1: Semantic search (retrieve a wider candidate pool) ──────────
    sem_results = collection.query(
        query_texts=[query],
        n_results=min(n_candidates, collection.count()),
        include=["documents", "metadatas", "distances"],
    )

    if not sem_results["documents"][0]:
        return f"No results found for: \"{query}\"\n\nThe knowledge base may not cover this topic."

    # Build candidate dict keyed by chunk_id
    # {chunk_id: {"doc": str, "meta": dict, "sem_score": float, "bm25_score": float}}
    candidates = {}
    for doc, meta, dist in zip(
        sem_results["documents"][0],
        sem_results["metadatas"][0],
        sem_results["distances"][0],
    ):
        chunk_id = f"{meta['video_id']}_chunk_{meta['chunk_index']:04d}"
        candidates[chunk_id] = {
            "doc":       doc,
            "meta":      meta,
            "sem_score": max(0.0, 1.0 - dist / 2.0),
            "bm25_score": 0.0,
        }

    # ── Step 2: BM25 scoring ───────────────────────────────────────────────
    bm25_building = not _bm25_ready.is_set() and _bm25_index is None
    if _bm25_index is not None:
        bm25_raw = _bm25_index.get_scores(query.lower().split())

        # Get top-n_candidates by BM25 and merge into candidates
        top_bm25_idx = sorted(range(len(bm25_raw)), key=lambda i: bm25_raw[i], reverse=True)[:n_candidates]
        bm25_only_ids = []
        for idx in top_bm25_idx:
            cid = _bm25_ids[idx]
            if cid not in candidates:
                bm25_only_ids.append(cid)
                candidates[cid] = {
                    "doc":       _bm25_docs[idx],
                    "meta":      None,   # fetch below
                    "sem_score": 0.0,
                    "bm25_score": 0.0,
                }
            candidates[cid]["bm25_score"] = float(bm25_raw[idx])

        # Fetch metadata for BM25-only chunks
        if bm25_only_ids:
            fetched = collection.get(ids=bm25_only_ids, include=["metadatas"])
            for cid, meta in zip(fetched["ids"], fetched["metadatas"]):
                candidates[cid]["meta"] = meta

        # Remove candidates where metadata fetch failed
        candidates = {k: v for k, v in candidates.items() if v["meta"] is not None}

        # Normalize BM25 scores to [0, 1] over this candidate set
        bm25_vals = [v["bm25_score"] for v in candidates.values()]
        bm25_max  = max(bm25_vals) if bm25_vals else 1.0
        bm25_min  = min(bm25_vals) if bm25_vals else 0.0
        bm25_range = bm25_max - bm25_min or 1.0
        for v in candidates.values():
            v["bm25_norm"] = (v["bm25_score"] - bm25_min) / bm25_range
    else:
        for v in candidates.values():
            v["bm25_norm"] = 0.0

    # ── Step 3: Video-level metadata boost ────────────────────────────────
    boosted_video_ids = set()
    if _meta_collection is not None:
        try:
            meta_results = _meta_collection.query(
                query_texts=[query],
                n_results=min(10, _meta_collection.count()),
                include=["metadatas"],
            )
            for meta in meta_results["metadatas"][0]:
                vid_id = meta.get("video_id")
                if vid_id:
                    boosted_video_ids.add(vid_id)
        except Exception as e:
            logger.warning(f"Meta collection query failed: {e}")

    # ── Step 4: Combine scores ─────────────────────────────────────────────
    for v in candidates.values():
        combined = 0.4 * v["bm25_norm"] + 0.6 * v["sem_score"]
        if v["meta"].get("video_id") in boosted_video_ids:
            combined += 0.2
        v["combined_score"] = combined

    # Sort and take top 30 for cross-encoder
    sorted_candidates = sorted(candidates.values(), key=lambda v: v["combined_score"], reverse=True)
    top30 = sorted_candidates[:30]

    # ── Step 5: Cross-encoder re-ranking ──────────────────────────────────
    if _cross_encoder is not None and len(top30) > 1:
        # Strip title prefix from doc for cleaner cross-encoder input
        def _chunk_text(doc):
            parts = doc.split("\n\n", 1)
            return parts[1] if len(parts) > 1 else doc

        pairs  = [(query, _chunk_text(v["doc"])) for v in top30]
        ce_scores = _cross_encoder.predict(pairs)
        for v, score in zip(top30, ce_scores):
            v["final_score"] = float(score)
        top30.sort(key=lambda v: v["final_score"], reverse=True)
    else:
        for v in top30:
            v["final_score"] = v["combined_score"]

    # ── Step 6: Format results ─────────────────────────────────────────────
    final = top30[:n_results]

    # Normalize final scores to [0, 1] for display
    final_max = max(v["final_score"] for v in final) if final else 1.0
    final_min = min(v["final_score"] for v in final) if final else 0.0
    final_range = final_max - final_min or 1.0

    chunks  = []
    sources = set()
    for i, v in enumerate(final):
        display_score = (v["final_score"] - final_min) / final_range
        chunks.append(_format_chunk(v["doc"], v["meta"], display_score, i))
        sources.add(v["meta"].get("video_title", "Unknown"))

    bm25_note = " (BM25 index building in background — rerun for hybrid results)" if bm25_building else ""
    header = (
        f"Found {len(chunks)} relevant excerpts from {len(sources)} video(s) "
        f"for: \"{query}\"{bm25_note}\n"
        f"Sources: {', '.join(sorted(sources))}\n\n"
    )
    return header + "\n".join(chunks)


@mcp.tool()
async def yt_get_video_context(
    video_title: str,
    topic: Optional[str] = None,
    n_results: int = 5,
) -> str:
    """Get transcript excerpts from a specific video in the knowledge base.

    Useful when you know which video has relevant info and want to dive deeper.
    Can filter by topic within that video.

    Args:
        video_title: Full or partial title of the video to search within.
        topic: Optional topic to focus on. If omitted, returns general content from the video.
        n_results: Number of chunks to return from this video, 1-20. Default 5.
    """
    collection = _get_collection()
    if collection is None:
        return f"Error: {_init_error}"

    n_results = max(1, min(n_results, 20))

    # Combine title + topic for semantic search, then filter by title match
    search_query = f"{topic} {video_title}" if topic else video_title
    results = collection.query(query_texts=[search_query], n_results=n_results * 3)

    # Filter to chunks matching the video title
    title_lower = video_title.lower()
    filtered = []
    for i in range(len(results["documents"][0])):
        meta = results["metadatas"][0][i]
        vid_title = meta.get("video_title", "").lower()
        if title_lower in vid_title or vid_title in title_lower:
            filtered.append((
                results["documents"][0][i],
                meta,
                results["distances"][0][i],
            ))

    if not filtered:
        all_titles = sorted(set(
            m.get("video_title", "Unknown") for m in results["metadatas"][0]
        ))
        return (
            f"No chunks matched \"{video_title}\".\n\n"
            f"Videos found in results:\n"
            + "\n".join(f"  - {t}" for t in all_titles)
            + "\n\nUse yt_list_videos to see all available videos."
        )

    filtered = filtered[:n_results]
    chunks = [
        _format_chunk(doc, meta, max(0.0, 1.0 - dist / 2.0), i)
        for i, (doc, meta, dist) in enumerate(filtered)
    ]

    matched_title = filtered[0][1].get("video_title", "Unknown")
    header = f"Found {len(filtered)} excerpts from \"{matched_title}\""
    if topic:
        header += f" about \"{topic}\""
    return header + "\n\n" + "\n".join(chunks)


@mcp.tool()
async def yt_list_videos(channel_filter: Optional[str] = None) -> str:
    """List videos indexed in the knowledge base.

    Without channel_filter: returns a compact CHANNEL SUMMARY showing each channel's
    video count and chunk count (~5KB). Use this first to discover what's available.

    With channel_filter='@channel': returns the video list for that specific channel
    in a compact format — one line per video with ID, title, and chunk count.
    Use the video ID with yt_get_video_context to deep-dive a specific video.

    Args:
        channel_filter: Channel handle to list videos for (e.g. '@ycombinator').
                        Omit to get a channel-level summary of the whole library.
    """
    collection = _get_collection()
    if collection is None:
        return f"Error: {_init_error}"

    total_chunks = collection.count()

    # ── Fast path: SQLite available ───────────────────────────────────────────────
    conn = _get_sqlite()
    if conn is not None:

        if channel_filter:
            # Per-channel compact video list
            rows = conn.execute(
                "SELECT id, title, channel_handle FROM videos WHERE has_transcript=1"
                " AND LOWER(channel_handle) LIKE LOWER(?)"
                " ORDER BY title",
                [f"%{channel_filter.lstrip('@').lower()}%"],
            ).fetchall()
            conn.close()

            if not rows:
                return f"No videos found for channel matching '{channel_filter}'."

            chunk_counts    = _get_chunk_counts_from_meta()
            ch              = rows[0]["channel_handle"]
            total_ch_chunks = sum(chunk_counts.get(r["id"], 0) for r in rows)

            lines = [
                f"{ch} — {len(rows)} videos | {total_ch_chunks:,} chunks",
                f"YouTube: https://www.youtube.com/@{ch.lstrip('@')}",
                f"(Use yt_get_video_context with the video ID to search within a video)",
                "",
            ]
            for row in rows:
                n_ch  = chunk_counts.get(row["id"], 0)
                title = (row["title"] or "Unknown")[:80]
                lines.append(f"[{row['id']}] {title}  {n_ch}ch")

        else:
            # Channel-level summary (default) — tiny output
            ch_rows = conn.execute(
                "SELECT channel_handle, COUNT(*) as video_count"
                " FROM videos WHERE has_transcript=1"
                " GROUP BY channel_handle ORDER BY channel_handle"
            ).fetchall()
            conn.close()

            # Per-channel chunk totals from meta_collection
            ch_chunks: dict = {}
            if _meta_collection is not None:
                try:
                    mc    = _meta_collection.count()
                    batch = 5_000
                    for offset in range(0, mc, batch):
                        data = _meta_collection.get(limit=batch, offset=offset, include=["metadatas"])
                        for m in data["metadatas"]:
                            ch_h = m.get("channel_name", "")
                            if ch_h:
                                ch_chunks[ch_h] = ch_chunks.get(ch_h, 0) + m.get("chunk_count", 0)
                except Exception:
                    pass

            total_v = sum(r["video_count"] for r in ch_rows)
            lines = [
                f"Knowledge Base: {total_chunks:,} chunks | {total_v} videos | {len(ch_rows)} channels",
                "",
                "CHANNEL SUMMARY  (pass channel_filter='@channel' to list its videos):",
            ]
            for r in ch_rows:
                ch  = r["channel_handle"]
                cch = ch_chunks.get(ch, 0)
                lines.append(f"  {ch:<35} {r['video_count']:>4} videos | {cch:>6,} ch")

        return "\n".join(lines)

    # ── Fallback: no SQLite — paginated chunk scan ────────────────────────────────
    batch, all_metas = 10_000, []
    for offset in range(0, total_chunks, batch):
        data = collection.get(limit=batch, offset=offset, include=["metadatas"])
        all_metas.extend(data["metadatas"])

    # Build per-channel summary from chunks (same compact output)
    ch_video_ids: dict = {}
    ch_chunk_counts: dict = {}
    for meta in all_metas:
        channel  = meta.get("channel_name", meta.get("channel_handle", "unknown"))
        video_id = meta.get("video_id", "")
        if channel not in ch_video_ids:
            ch_video_ids[channel]     = set()
            ch_chunk_counts[channel]  = 0
        if video_id:
            ch_video_ids[channel].add(video_id)
        ch_chunk_counts[channel] += 1

    if channel_filter:
        cf_lower = channel_filter.lower().lstrip("@")
        matched  = {ch: ids for ch, ids in ch_video_ids.items() if cf_lower in ch.lower()}
        if not matched:
            return f"No videos found for channel matching '{channel_filter}'."
        ch   = next(iter(matched))
        vids = sorted(matched[ch])
        lines = [f"{ch} — {len(vids)} videos | {ch_chunk_counts[ch]:,} chunks", ""]
        for vid in vids:
            lines.append(f"[{vid}] (title unavailable in fallback mode)")
    else:
        total_v = sum(len(ids) for ids in ch_video_ids.values())
        lines = [
            f"Knowledge Base: {total_chunks:,} chunks | {total_v} videos | {len(ch_video_ids)} channels",
            "",
            "CHANNEL SUMMARY:",
        ]
        for ch in sorted(ch_video_ids):
            lines.append(f"  {ch:<35} {len(ch_video_ids[ch]):>4} videos | {ch_chunk_counts[ch]:>6,} ch")

    return "\n".join(lines)


# ─────────────────────────────────────────
# SQLITE CONNECTION  (audit tools)
# ─────────────────────────────────────────

def _get_chunk_counts_from_meta() -> dict:
    """Return {video_id: chunk_count} from meta_collection. Empty dict if unavailable."""
    if _meta_collection is None:
        return {}
    counts = {}
    try:
        mc    = _meta_collection.count()
        batch = 5_000
        for offset in range(0, mc, batch):
            data = _meta_collection.get(limit=batch, offset=offset, include=["metadatas"])
            for m in data["metadatas"]:
                vid = m.get("video_id", "")
                if vid:
                    counts[vid] = m.get("chunk_count", 0)
    except Exception:
        pass
    return counts


def _get_sqlite():
    """Open a read-only SQLite connection. Returns None if DB not found."""
    if not os.path.exists(SQLITE_DB_PATH):
        return None
    try:
        conn = sqlite3.connect(f"file:{SQLITE_DB_PATH}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        return conn
    except Exception:
        return None


def _fmt_views(n):
    if n is None:       return "?"
    if n >= 1_000_000:  return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:      return f"{n / 1_000:.0f}K"
    return str(n)


def _fmt_dur(seconds):
    if not seconds: return "?"
    h, rem = divmod(int(seconds), 3600)
    m = rem // 60
    return f"{h}h{m:02d}m" if h else f"{m}m"


# Keywords in titles that suggest off-topic / low-quality content
_SUSPICIOUS_TITLE_KEYWORDS = [
    "#shorts", "shorts", " live", "livestream", "live stream", "live q&a",
    "reaction", "reacting to", "vlog", "daily vlog", "day in my life",
    "unboxing", "announcement", "compilation", "highlights", " clip ",
    "q&a", "q & a", " ama", "ask me anything",
    "csgo", "minecraft", "fortnite", "valorant", "gaming", "playthrough",
    "tier list", "meme review", "roast", "mukbang", "asmr",
]


@mcp.tool()
async def yt_audit_channel(channel: str, sort_by: str = "views") -> str:
    """List every video from a channel with view counts, duration, and transcript status.

    Use this to review a channel's full content and manually spot anything
    off-topic or low-quality. For automated flagging use yt_scan_for_issues.

    After reviewing, you can tell the user which video IDs look suspicious so
    they can remove them with: python pipeline.py remove-video <video_id>

    Args:
        channel: Channel handle (e.g. '@ycombinator') or partial name. Case-insensitive.
        sort_by: 'views' (default, highest first), 'duration' (longest first), or 'title' (A-Z)
    """
    conn = _get_sqlite()
    if conn is None:
        return (
            f"SQLite DB not found at: {SQLITE_DB_PATH}\n"
            f"Add SQLITE_DB_PATH to your MCP server env config pointing to knowledge.db"
        )

    rows = conn.execute(
        "SELECT id, title, view_count, duration, has_transcript, url, channel_handle "
        "FROM videos WHERE LOWER(channel_handle) LIKE LOWER(?)",
        (f"%{channel.lstrip('@').lower()}%",),
    ).fetchall()
    conn.close()

    if not rows:
        return f"No videos found for channel matching '{channel}'."

    if sort_by == "views":
        rows = sorted(rows, key=lambda r: r["view_count"] or 0, reverse=True)
    elif sort_by == "duration":
        rows = sorted(rows, key=lambda r: r["duration"] or 0, reverse=True)
    else:
        rows = sorted(rows, key=lambda r: (r["title"] or "").lower())

    channel_handle = rows[0]["channel_handle"]
    has_trans = sum(1 for r in rows if r["has_transcript"])

    lines = [
        f"CHANNEL AUDIT: {channel_handle}",
        f"{len(rows)} videos | {has_trans} with transcripts | {len(rows) - has_trans} without",
        f"Sorted by: {sort_by}",
        "",
    ]

    for r in rows:
        trans = "ok" if r["has_transcript"] else "NO TRANSCRIPT"
        url   = r["url"] or f"https://www.youtube.com/watch?v={r['id']}"
        lines.append(
            f"[{trans}] {_fmt_views(r['view_count'])} views | {_fmt_dur(r['duration'])} | {r['title'] or 'Unknown'}"
        )
        lines.append(f"    id={r['id']}  {url}")

    return "\n".join(lines)


@mcp.tool()
async def yt_scan_for_issues(channel: str, expected_topics: str = "") -> str:
    """Automatically scan a channel's videos for quality and relevance issues.

    Runs heuristic checks and flags videos that may be off-topic or low-quality:
      - Suspicious title keywords (shorts, reaction, gaming, vlog, live stream, etc.)
      - Low engagement: view count < 10% of the channel's median
      - Missing transcript (no text to search)

    If expected_topics is provided, include it in your judgment when reviewing
    the flagged list — the automated checks catch obvious signals but you should
    reason about topic fit for the borderline cases.

    Args:
        channel: Channel handle (e.g. '@hubermanlab') or partial name.
        expected_topics: Comma-separated topics this channel should cover
                         (e.g. 'neuroscience, sleep, fitness, hormones').
                         Helps you reason about off-topic titles in the results.
    """
    conn = _get_sqlite()
    if conn is None:
        return f"SQLite DB not found at: {SQLITE_DB_PATH}"

    rows = conn.execute(
        "SELECT id, title, view_count, duration, has_transcript, url, channel_handle "
        "FROM videos WHERE LOWER(channel_handle) LIKE LOWER(?)",
        (f"%{channel.lstrip('@').lower()}%",),
    ).fetchall()
    conn.close()

    if not rows:
        return f"No videos found for channel matching '{channel}'."

    channel_handle = rows[0]["channel_handle"]

    # Median view count for relative low-engagement detection
    view_counts = sorted(r["view_count"] for r in rows if r["view_count"] is not None)
    median_views = view_counts[len(view_counts) // 2] if view_counts else 0
    low_threshold = median_views * 0.10

    flagged_keywords  = []
    flagged_low_views = []
    flagged_no_trans  = []

    for r in rows:
        title_lower = (r["title"] or "").lower()
        url = r["url"] or f"https://www.youtube.com/watch?v={r['id']}"
        entry = f"  {r['title']}\n    id={r['id']} | {_fmt_views(r['view_count'])} views | {_fmt_dur(r['duration'])} | {url}"

        # Suspicious title keyword
        for kw in _SUSPICIOUS_TITLE_KEYWORDS:
            if kw in title_lower:
                flagged_keywords.append(f"  [{kw.strip()}] {r['title']}\n    id={r['id']} | {url}")
                break

        # Low engagement (only meaningful if channel has decent views overall)
        if r["view_count"] is not None and median_views >= 5_000 and r["view_count"] < low_threshold:
            flagged_low_views.append(entry)

        # No transcript
        if not r["has_transcript"]:
            flagged_no_trans.append(entry)

    lines = [
        f"ISSUE SCAN: {channel_handle}",
        f"Total videos: {len(rows)} | Median views: {_fmt_views(median_views)}",
    ]
    if expected_topics:
        lines.append(f"Expected topics: {expected_topics}")
        lines.append("(Review flagged titles below with these topics in mind)")
    lines.append("")

    if flagged_keywords:
        lines.append(f"SUSPICIOUS TITLES ({len(flagged_keywords)} videos — keyword match):")
        lines.extend(flagged_keywords)
        lines.append("")

    if flagged_low_views:
        lines.append(f"LOW ENGAGEMENT ({len(flagged_low_views)} videos — <10% of median {_fmt_views(median_views)} views):")
        lines.extend(flagged_low_views)
        lines.append("")

    if flagged_no_trans:
        lines.append(f"NO TRANSCRIPT ({len(flagged_no_trans)} videos — not searchable):")
        lines.extend(flagged_no_trans)
        lines.append("")

    total = len(flagged_keywords) + len(flagged_low_views) + len(flagged_no_trans)
    if total == 0:
        lines.append("No issues detected. Channel looks clean.")
    else:
        lines.append(f"{total} flags total (a video may appear in multiple categories).")
        lines.append("To remove a video: python pipeline.py remove-video <video_id>")

    return "\n".join(lines)


# ─────────────────────────────────────────
# RUN (stdio transport for Claude Desktop)
# ─────────────────────────────────────────

if __name__ == "__main__":
    mcp.run()
