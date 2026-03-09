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
            "CHROMA_COLLECTION": "transcripts"
          }
        }
      }
    }

    Then restart Claude Desktop. You should see a hammer icon with the tools available.
"""

import os
import sys
import logging
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

        # Build BM25 index now that we have the collection
        _build_bm25_index()

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
# BM25 INDEX
# ─────────────────────────────────────────

_bm25_index = None
_bm25_ids   = []   # parallel list of chunk IDs
_bm25_docs  = []   # parallel list of raw doc strings (for cross-encoder)


def _build_bm25_index():
    """Build an in-memory BM25 index from all ChromaDB chunk documents."""
    global _bm25_index, _bm25_ids, _bm25_docs

    if _collection is None:
        return
    count = _collection.count()
    if count == 0:
        return

    logger.info(f"Building BM25 index over {count} chunks...")
    batch = 10_000
    all_ids, all_docs = [], []
    for offset in range(0, count, batch):
        data = _collection.get(limit=batch, offset=offset, include=["documents"])
        all_ids.extend(data["ids"])
        all_docs.extend(data["documents"])

    _bm25_ids  = all_ids
    _bm25_docs = all_docs
    tokenized  = [doc.lower().split() for doc in _bm25_docs]
    _bm25_index = BM25Okapi(tokenized)
    logger.info("BM25 index ready")


# ─────────────────────────────────────────
# CROSS-ENCODER  (loaded eagerly at startup)
# ─────────────────────────────────────────

_cross_encoder = None


def _load_cross_encoder():
    global _cross_encoder
    logger.info("Loading cross-encoder model (cross-encoder/ms-marco-MiniLM-L-6-v2)...")
    _cross_encoder = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
    logger.info("Cross-encoder ready")


_load_cross_encoder()


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

    header = (
        f"Found {len(chunks)} relevant excerpts from {len(sources)} video(s) "
        f"for: \"{query}\"\n"
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
    """List all videos indexed in the knowledge base.

    Shows video titles, chunk counts, channels, and YouTube links.
    Use this to discover available content before searching, or to get
    the exact title for yt_get_video_context.

    Args:
        channel_filter: Optional channel handle to filter by (e.g. '@ycombinator').
    """
    collection = _get_collection()
    if collection is None:
        return f"Error: {_init_error}"

    total_chunks = collection.count()

    # Paginate through ALL chunks — a per-request cap caused only a fraction of videos to appear
    batch = 10_000
    all_metas = []
    for offset in range(0, total_chunks, batch):
        data = collection.get(limit=batch, offset=offset, include=["metadatas"])
        all_metas.extend(data["metadatas"])

    videos   = {}
    channels = set()
    for meta in all_metas:
        title    = meta.get("video_title", "Unknown")
        video_id = meta.get("video_id", "")
        channel  = meta.get("channel_name", meta.get("channel", meta.get("channel_handle", "")))

        if channel:
            channels.add(channel)
        if channel_filter and channel_filter.lower() not in channel.lower():
            continue

        if title not in videos:
            videos[title] = {
                "chunks":  meta.get("total_chunks", 0),
                "channel": channel,
                "video_id": video_id,
            }

    lines = [f"YouTube Knowledge Base — {total_chunks} total chunks across {len(videos)} videos"]
    if channels:
        lines.append(f"Channels: {', '.join(sorted(channels))}")
    if channel_filter:
        lines.append(f"Filter: {channel_filter}")
    lines.append("")

    for title in sorted(videos):
        info = videos[title]
        url  = f"https://www.youtube.com/watch?v={info['video_id']}" if info["video_id"] else ""
        lines.append(f"- {title}")
        lines.append(f"  {info['chunks']} chunks | {info['channel']} | {url}")

    return "\n".join(lines)


# ─────────────────────────────────────────
# RUN (stdio transport for Claude Desktop)
# ─────────────────────────────────────────

if __name__ == "__main__":
    mcp.run()
