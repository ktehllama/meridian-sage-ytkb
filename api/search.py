"""
api/search.py
=============
Hybrid search engine: ChromaDB semantic search + BM25 keyword search.

IMPORTANT: This module is self-contained. Do NOT import yt_knowledge_mcp.py —
the search logic is copied here inline to avoid BM25 background-thread side-effects
that trigger at module import time in the MCP server.

Startup:
    Call init_search() once from FastAPI lifespan before serving requests.

Usage:
    results = hybrid_search("how to find product market fit", n_results=8)
"""

import logging
import pickle
import sqlite3
import threading
from typing import Optional

import chromadb
from rank_bm25 import BM25Okapi

from api.config import config

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────
# Module-level singletons — populated by init_search()
# ─────────────────────────────────────────────────────────────

_collection: Optional[chromadb.Collection] = None
_bm25_index: Optional[BM25Okapi] = None
_bm25_chunk_ids: list[str] = []   # parallel to BM25 corpus — chunk_ids
_bm25_docs: list[str] = []        # parallel to BM25 corpus — raw doc strings
_bm25_ready = threading.Event()
_bm25_lock  = threading.Lock()
_init_error: Optional[str] = None


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────

def _seconds_to_timestamp(seconds: float) -> str:
    """Convert float seconds to MM:SS or HH:MM:SS string."""
    s = int(seconds)
    if s >= 3600:
        return f"{s // 3600}:{(s % 3600) // 60:02d}:{s % 60:02d}"
    return f"{s // 60}:{s % 60:02d}"


def _get_sqlite_conn() -> Optional[sqlite3.Connection]:
    """Open a read-only SQLite connection. Returns None if DB not accessible."""
    import os
    if not os.path.exists(config.SQLITE_DB_PATH):
        return None
    try:
        conn = sqlite3.connect(f"file:{config.SQLITE_DB_PATH}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        return conn
    except Exception as e:
        logger.warning(f"SQLite open failed: {e}")
        return None


# ─────────────────────────────────────────────────────────────
# Initialisation (called once at startup)
# ─────────────────────────────────────────────────────────────

def init_search() -> None:
    """
    Connect to ChromaDB and build the BM25 index.
    Called synchronously from FastAPI lifespan — blocks until ready.
    Raises RuntimeError if ChromaDB is unreachable.
    """
    global _collection, _bm25_index, _bm25_chunk_ids, _bm25_docs, _init_error

    import os

    # ── 1. Connect ChromaDB ───────────────────────────────────
    if not os.path.exists(config.CHROMA_DB_PATH):
        _init_error = f"ChromaDB directory not found: {config.CHROMA_DB_PATH}"
        raise RuntimeError(_init_error)

    try:
        logger.info(f"Connecting to ChromaDB at {config.CHROMA_DB_PATH} ...")
        client = chromadb.PersistentClient(path=config.CHROMA_DB_PATH)
        _collection = client.get_collection(name=config.CHROMA_COLLECTION)
        chunk_count = _collection.count()
        logger.info(f"ChromaDB connected — {chunk_count:,} chunks in '{config.CHROMA_COLLECTION}'")
    except Exception as e:
        _init_error = f"ChromaDB init failed: {e}"
        logger.error(_init_error)
        raise RuntimeError(_init_error)

    # ── 2. Build BM25 in background — don't block startup ─────
    threading.Thread(target=_build_bm25_background, daemon=True).start()


def _build_bm25_background() -> None:
    """Build BM25 index in background thread. Uses pickle cache keyed by chunk count."""
    global _bm25_index, _bm25_chunk_ids, _bm25_docs

    if _collection is None:
        _bm25_ready.set()
        return

    total = _collection.count()
    if total == 0:
        _bm25_ready.set()
        return

    cache_path = config.BM25_CACHE_PATH

    # Try loading from disk cache
    if cache_path and __import__("os").path.exists(cache_path):
        try:
            with open(cache_path, "rb") as f:
                cached = pickle.load(f)
            if cached.get("chunk_count") == total:
                with _bm25_lock:
                    _bm25_chunk_ids = cached["ids"]
                    _bm25_docs      = cached["docs"]
                    _bm25_index     = cached["index"]
                logger.info(f"BM25 loaded from cache ({total:,} chunks)")
                _bm25_ready.set()
                return
        except Exception as e:
            logger.warning(f"BM25 cache load failed, rebuilding: {e}")

    # Build from scratch
    logger.info(f"Building BM25 index over {total:,} chunks (background) ...")
    all_ids: list[str] = []
    all_docs: list[str] = []
    batch_size = 10_000
    try:
        for offset in range(0, total, batch_size):
            data = _collection.get(limit=batch_size, offset=offset, include=["documents"])
            all_ids.extend(data["ids"])
            all_docs.extend(data["documents"])

        tokenized = [doc.lower().split() for doc in all_docs]
        index = BM25Okapi(tokenized)

        with _bm25_lock:
            _bm25_chunk_ids = all_ids
            _bm25_docs      = all_docs
            _bm25_index     = index

        logger.info(f"BM25 index ready — {len(all_ids):,} chunks")

        # Save cache
        if cache_path:
            try:
                with open(cache_path, "wb") as f:
                    pickle.dump({"chunk_count": total, "ids": all_ids, "docs": all_docs, "index": index}, f)
                logger.info(f"BM25 cache saved to {cache_path}")
            except Exception as e:
                logger.warning(f"BM25 cache save failed: {e}")
    except Exception as e:
        logger.warning(f"BM25 build failed (semantic-only mode): {e}")
    finally:
        _bm25_ready.set()


def get_collection() -> Optional[chromadb.Collection]:
    """Return the ChromaDB collection, or None if not initialised."""
    return _collection


def get_chunk_count() -> int:
    """Return number of chunks in the collection, or 0 if unavailable."""
    if _collection is None:
        return 0
    try:
        return _collection.count()
    except Exception:
        return 0


def get_db_video_count() -> int:
    """Return number of videos with transcripts in SQLite, or 0 if unavailable."""
    conn = _get_sqlite_conn()
    if conn is None:
        return 0
    try:
        row = conn.execute("SELECT COUNT(*) as c FROM videos WHERE has_transcript=1").fetchone()
        return row["c"] if row else 0
    except Exception:
        return 0
    finally:
        conn.close()


# ─────────────────────────────────────────────────────────────
# Core search function
# ─────────────────────────────────────────────────────────────

def hybrid_search(query: str, n_results: int = 8) -> list[dict]:
    """
    Run hybrid search (semantic + BM25) and return top n_results chunks.

    Returns list of dicts, sorted by combined score descending:
        {
            chunk_id: str,
            title: str,
            text: str,
            start_time: float,
            timestamp_str: str,
            timestamp_url: str,
            score: float,        # combined score [0,1]
        }

    Returns empty list if collection is unavailable or no results found.
    """
    if _collection is None:
        logger.error("hybrid_search called before init_search()")
        return []

    n_candidates = max(30, n_results * 4)
    safe_n = min(n_candidates, _collection.count())
    if safe_n == 0:
        return []

    # ── Step 1: Semantic search ───────────────────────────────
    try:
        sem_results = _collection.query(
            query_texts=[query],
            n_results=safe_n,
            include=["documents", "metadatas", "distances"],
        )
    except Exception as e:
        logger.error(f"ChromaDB query failed: {e}")
        return []

    docs_list = sem_results["documents"][0]
    metas_list = sem_results["metadatas"][0]
    dists_list = sem_results["distances"][0]

    if not docs_list:
        return []

    # Build candidate dict keyed by chunk_id
    candidates: dict[str, dict] = {}
    for doc, meta, dist in zip(docs_list, metas_list, dists_list):
        chunk_idx = meta.get("chunk_index", 0)
        video_id = meta.get("video_id", "")
        chunk_id = f"{video_id}_chunk_{int(chunk_idx):04d}"
        candidates[chunk_id] = {
            "chunk_id": chunk_id,
            "doc": doc,
            "meta": meta,
            "sem_score": max(0.0, 1.0 - dist / 2.0),
            "bm25_score": 0.0,
            "bm25_norm": 0.0,
        }

    # ── Step 2: BM25 scoring ──────────────────────────────────
    with _bm25_lock:
        bm25_index_snap = _bm25_index
        bm25_ids_snap   = _bm25_chunk_ids

    if bm25_index_snap is not None and bm25_ids_snap:
        try:
            bm25_raw = bm25_index_snap.get_scores(query.lower().split())
            # Take top candidates by BM25 score
            top_bm25_idx = sorted(
                range(len(bm25_raw)),
                key=lambda i: bm25_raw[i],
                reverse=True,
            )[:n_candidates]

            # Fetch metadata for BM25-only chunks (not already in candidates)
            bm25_only_ids = []
            for idx in top_bm25_idx:
                cid = bm25_ids_snap[idx]
                if cid not in candidates:
                    bm25_only_ids.append((idx, cid))
                else:
                    candidates[cid]["bm25_score"] = float(bm25_raw[idx])

            # Fetch metadata for new BM25-only chunks
            if bm25_only_ids:
                fetch_ids = [cid for _, cid in bm25_only_ids]
                try:
                    fetched = _collection.get(
                        ids=fetch_ids,
                        include=["documents", "metadatas"],
                    )
                    fetched_map = {
                        fid: (fdoc, fmeta)
                        for fid, fdoc, fmeta in zip(
                            fetched["ids"],
                            fetched["documents"],
                            fetched["metadatas"],
                        )
                    }
                except Exception:
                    fetched_map = {}

                for idx, cid in bm25_only_ids:
                    if cid in fetched_map:
                        fdoc, fmeta = fetched_map[cid]
                        candidates[cid] = {
                            "chunk_id": cid,
                            "doc": fdoc,
                            "meta": fmeta,
                            "sem_score": 0.0,
                            "bm25_score": float(bm25_raw[idx]),
                            "bm25_norm": 0.0,
                        }


            # Normalize BM25 scores to [0, 1] over the full candidate set
            bm25_vals = [v["bm25_score"] for v in candidates.values()]
            bm25_max = max(bm25_vals) if bm25_vals else 1.0
            bm25_min = min(bm25_vals) if bm25_vals else 0.0
            bm25_range = bm25_max - bm25_min or 1.0
            for v in candidates.values():
                v["bm25_norm"] = (v["bm25_score"] - bm25_min) / bm25_range

        except Exception as e:
            logger.warning(f"BM25 scoring failed, using semantic only: {e}")

    # ── Step 3: Combine scores and rank ───────────────────────
    for v in candidates.values():
        v["combined_score"] = 0.7 * v["sem_score"] + 0.3 * v["bm25_norm"]

    # Remove candidates with missing metadata
    candidates = {k: v for k, v in candidates.items() if v.get("meta") is not None}

    sorted_candidates = sorted(
        candidates.values(),
        key=lambda v: v["combined_score"],
        reverse=True,
    )
    top = sorted_candidates[:n_results]

    # ── Step 4: Format results ────────────────────────────────
    results = []
    for v in top:
        meta = v["meta"]
        doc = v["doc"]
        title = meta.get("video_title", "Unknown Video")
        start_time = float(meta.get("start_time", 0))
        timestamp_url = meta.get("timestamp_url", "")

        # Fallback timestamp URL construction
        if not timestamp_url:
            video_id = meta.get("video_id", "")
            if video_id:
                timestamp_url = f"https://www.youtube.com/watch?v={video_id}&t={int(start_time)}s"

        # Strip title prefix from doc (format: "Title\n\nchunk text")
        parts = doc.split("\n\n", 1)
        text = parts[1] if len(parts) > 1 else doc

        results.append({
            "chunk_id": v["chunk_id"],
            "title": title,
            "text": text,
            "start_time": start_time,
            "timestamp_str": _seconds_to_timestamp(start_time),
            "timestamp_url": timestamp_url,
            "score": v["combined_score"],
        })

    return results


# ─────────────────────────────────────────────────────────────
# Video / channel listing (SQLite reads)
# ─────────────────────────────────────────────────────────────

def list_videos(
    channel: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[dict], int]:
    """
    Return (videos, total_count) from SQLite.
    Filter by channel handle (partial, case-insensitive) if provided.
    """
    conn = _get_sqlite_conn()
    if conn is None:
        return [], 0

    try:
        where = "WHERE has_transcript=1"
        params: list = []
        if channel:
            where += " AND LOWER(channel_handle) LIKE LOWER(?)"
            params.append(f"%{channel.lstrip('@')}%")

        total_row = conn.execute(
            f"SELECT COUNT(*) as c FROM videos {where}", params
        ).fetchone()
        total = total_row["c"] if total_row else 0

        rows = conn.execute(
            f"SELECT id, title, channel_handle, url, duration FROM videos {where}"
            " ORDER BY title LIMIT ? OFFSET ?",
            params + [limit, offset],
        ).fetchall()

        videos = [
            {
                "id": r["id"],
                "title": r["title"] or "Unknown",
                "channel": r["channel_handle"] or "",
                "url": r["url"] or f"https://www.youtube.com/watch?v={r['id']}",
                "duration": r["duration"],
            }
            for r in rows
        ]
        return videos, total
    except Exception as e:
        logger.error(f"list_videos query failed: {e}")
        return [], 0
    finally:
        conn.close()


def get_random_fact() -> dict | None:
    """
    Return a random transcript chunk as a "fun fact" for the homescreen.
    Picks a random offset into the ChromaDB collection and returns one chunk.
    Returns None if the collection is unavailable or empty.
    """
    import random as _random

    if _collection is None:
        return None
    try:
        total = _collection.count()
        if total == 0:
            return None

        offset = _random.randint(0, max(0, total - 1))
        result = _collection.get(
            limit=1,
            offset=offset,
            include=["documents", "metadatas"],
        )
        if not result["ids"]:
            return None

        doc = result["documents"][0]
        meta = result["metadatas"][0]

        title = meta.get("video_title", "Unknown Video")
        channel = meta.get("channel_name", "")
        start_time = float(meta.get("start_time", 0))
        timestamp_url = meta.get("timestamp_url", "")
        video_id = meta.get("video_id", "")

        if not timestamp_url and video_id:
            timestamp_url = f"https://www.youtube.com/watch?v={video_id}&t={int(start_time)}s"

        # Strip title prefix from doc (format: "Title\n\nchunk text")
        parts = doc.split("\n\n", 1)
        text = parts[1] if len(parts) > 1 else doc

        # Trim text to a readable excerpt (~300 chars)
        excerpt = text[:300].rstrip()
        if len(text) > 300:
            excerpt += "..."

        return {
            "title": title,
            "channel": channel,
            "excerpt": excerpt,
            "timestamp_str": _seconds_to_timestamp(start_time),
            "url": timestamp_url,
        }
    except Exception as e:
        logger.warning(f"get_random_fact failed: {e}")
        return None


def list_channels() -> list[dict]:
    """Return list of {name, video_count} from SQLite."""
    conn = _get_sqlite_conn()
    if conn is None:
        return []

    try:
        rows = conn.execute(
            "SELECT channel_handle, COUNT(*) as video_count"
            " FROM videos WHERE has_transcript=1"
            " GROUP BY channel_handle ORDER BY channel_handle"
        ).fetchall()
        return [{"name": r["channel_handle"], "video_count": r["video_count"]} for r in rows]
    except Exception as e:
        logger.error(f"list_channels query failed: {e}")
        return []
    finally:
        conn.close()
