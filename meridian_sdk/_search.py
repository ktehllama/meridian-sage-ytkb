"""
meridian_sdk/_search.py
=======================
Standalone hybrid search engine: ChromaDB semantic + BM25 keyword.
No dependency on api/.
"""

import logging
import pickle
import sqlite3
import threading
from typing import Optional

import chromadb
from rank_bm25 import BM25Okapi

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────
# State (populated by init())
# ─────────────────────────────────────────────────────────────

_collection: Optional[chromadb.Collection] = None
_bm25_index: Optional[BM25Okapi] = None
_bm25_chunk_ids: list[str] = []
_bm25_docs: list[str] = []
_bm25_ready = threading.Event()
_bm25_lock = threading.Lock()


def _ts(seconds: float) -> str:
    s = int(seconds)
    if s >= 3600:
        return f"{s // 3600}:{(s % 3600) // 60:02d}:{s % 60:02d}"
    return f"{s // 60}:{s % 60:02d}"


# ─────────────────────────────────────────────────────────────
# Init
# ─────────────────────────────────────────────────────────────

def init(
    chroma_path: str,
    collection_name: str,
    bm25_cache_path: str,
    wait_for_bm25: bool = False,
) -> None:
    """
    Connect to ChromaDB and start building BM25 index in background.
    Call once before using search().
    Raises RuntimeError if ChromaDB is unreachable.
    """
    global _collection

    import os
    if not os.path.exists(chroma_path):
        raise RuntimeError(f"ChromaDB directory not found: {chroma_path}")

    client = chromadb.PersistentClient(path=chroma_path)
    _collection = client.get_collection(name=collection_name)
    logger.info(f"ChromaDB connected — {_collection.count():,} chunks in '{collection_name}'")

    threading.Thread(
        target=_build_bm25,
        args=(bm25_cache_path,),
        daemon=True,
    ).start()

    if wait_for_bm25:
        _bm25_ready.wait()


def _build_bm25(cache_path: str) -> None:
    global _bm25_index, _bm25_chunk_ids, _bm25_docs

    if _collection is None:
        _bm25_ready.set()
        return

    total = _collection.count()
    if total == 0:
        _bm25_ready.set()
        return

    import os
    if cache_path and os.path.exists(cache_path):
        try:
            with open(cache_path, "rb") as f:
                cached = pickle.load(f)
            if cached.get("chunk_count") == total:
                with _bm25_lock:
                    _bm25_chunk_ids = cached["ids"]
                    _bm25_docs = cached["docs"]
                    _bm25_index = cached["index"]
                logger.info(f"BM25 loaded from cache ({total:,} chunks)")
                _bm25_ready.set()
                return
        except Exception as e:
            logger.warning(f"BM25 cache load failed, rebuilding: {e}")

    logger.info(f"Building BM25 index over {total:,} chunks ...")
    all_ids: list[str] = []
    all_docs: list[str] = []
    try:
        for offset in range(0, total, 10_000):
            data = _collection.get(limit=10_000, offset=offset, include=["documents"])
            all_ids.extend(data["ids"])
            all_docs.extend(data["documents"])

        index = BM25Okapi([doc.lower().split() for doc in all_docs])

        with _bm25_lock:
            _bm25_chunk_ids = all_ids
            _bm25_docs = all_docs
            _bm25_index = index

        logger.info(f"BM25 ready — {len(all_ids):,} chunks")

        if cache_path:
            try:
                with open(cache_path, "wb") as f:
                    pickle.dump(
                        {"chunk_count": total, "ids": all_ids, "docs": all_docs, "index": index},
                        f,
                    )
            except Exception as e:
                logger.warning(f"BM25 cache save failed: {e}")
    except Exception as e:
        logger.warning(f"BM25 build failed, semantic-only mode: {e}")
    finally:
        _bm25_ready.set()


# ─────────────────────────────────────────────────────────────
# Search
# ─────────────────────────────────────────────────────────────

def hybrid_search(query: str, n_results: int = 8) -> list[dict]:
    """
    Hybrid search (semantic + BM25). Returns up to n_results chunks sorted by score.

    Each result dict:
        chunk_id, title, text, start_time, timestamp_str, timestamp_url, score
    """
    if _collection is None:
        raise RuntimeError("Call init() before searching.")

    n_candidates = max(30, n_results * 4)
    safe_n = min(n_candidates, _collection.count())
    if safe_n == 0:
        return []

    # ── Semantic search ───────────────────────────────────────
    sem = _collection.query(
        query_texts=[query],
        n_results=safe_n,
        include=["documents", "metadatas", "distances"],
    )

    candidates: dict[str, dict] = {}
    for doc, meta, dist in zip(sem["documents"][0], sem["metadatas"][0], sem["distances"][0]):
        cid = f"{meta.get('video_id', '')}_chunk_{int(meta.get('chunk_index', 0)):04d}"
        candidates[cid] = {
            "chunk_id": cid,
            "doc": doc,
            "meta": meta,
            "sem_score": max(0.0, 1.0 - dist / 2.0),
            "bm25_score": 0.0,
            "bm25_norm": 0.0,
        }

    # ── BM25 scoring ──────────────────────────────────────────
    with _bm25_lock:
        bm25_snap = _bm25_index
        ids_snap = _bm25_chunk_ids

    if bm25_snap is not None and ids_snap:
        try:
            raw = bm25_snap.get_scores(query.lower().split())
            top_idx = sorted(range(len(raw)), key=lambda i: raw[i], reverse=True)[:n_candidates]

            bm25_only = [(i, ids_snap[i]) for i in top_idx if ids_snap[i] not in candidates]
            for i, cid in top_idx:
                if ids_snap[i] in candidates:
                    candidates[ids_snap[i]]["bm25_score"] = float(raw[i])

            if bm25_only:
                fetched = _collection.get(
                    ids=[cid for _, cid in bm25_only],
                    include=["documents", "metadatas"],
                )
                fm = {fid: (fd, fm) for fid, fd, fm in zip(
                    fetched["ids"], fetched["documents"], fetched["metadatas"]
                )}
                for i, cid in bm25_only:
                    if cid in fm:
                        fd, fmeta = fm[cid]
                        candidates[cid] = {
                            "chunk_id": cid, "doc": fd, "meta": fmeta,
                            "sem_score": 0.0, "bm25_score": float(raw[i]), "bm25_norm": 0.0,
                        }

            vals = [v["bm25_score"] for v in candidates.values()]
            bm25_range = (max(vals) - min(vals)) or 1.0
            bm25_min = min(vals)
            for v in candidates.values():
                v["bm25_norm"] = (v["bm25_score"] - bm25_min) / bm25_range
        except Exception as e:
            logger.warning(f"BM25 scoring failed, semantic-only: {e}")

    # ── Combine + rank ────────────────────────────────────────
    for v in candidates.values():
        v["combined_score"] = 0.7 * v["sem_score"] + 0.3 * v["bm25_norm"]

    top = sorted(candidates.values(), key=lambda v: v["combined_score"], reverse=True)[:n_results]

    results = []
    for v in top:
        meta = v["meta"]
        parts = v["doc"].split("\n\n", 1)
        text = parts[1] if len(parts) > 1 else v["doc"]
        start_time = float(meta.get("start_time", 0))
        ts_url = meta.get("timestamp_url") or (
            f"https://www.youtube.com/watch?v={meta.get('video_id', '')}&t={int(start_time)}s"
        )
        results.append({
            "chunk_id": v["chunk_id"],
            "title": meta.get("video_title", "Unknown Video"),
            "text": text,
            "start_time": start_time,
            "timestamp_str": _ts(start_time),
            "timestamp_url": ts_url,
            "score": v["combined_score"],
        })

    return results
