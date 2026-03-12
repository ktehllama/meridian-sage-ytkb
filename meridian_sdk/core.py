"""
meridian_sdk/core.py
====================
Main entry point. Completely standalone — no dependency on api/.

Usage:
    from meridian_sdk import Meridian

    m = Meridian()

    # raw: returns list of chunk dicts from the search engine, no LLM
    results = m.search("fundraising cold emails", mode="raw")

    # serious: LLM answer, terse and direct
    answer = m.search("how do you find product market fit", mode="serious")

    # chat: LLM answer, natural conversational tone (default)
    answer = m.search("what makes a good co-founder", mode="chat")

    # with sources dict
    result = m.search("hiring", mode="chat", show_sources=True)
    print(result["answer"])
    print(result["sources"])  # {"SRC_1": {"title": ..., "url": ...}, ...}

    # verbose: prints typo corrections, query variants, and loading steps
    answer = m.search("how do you find PMF", verbose=True)
"""

import logging
import os
import re
from typing import Literal

from meridian_sdk._search import init as _init_search
from meridian_sdk._search import hybrid_search
from meridian_sdk._llm import expand_query, synthesize

logger = logging.getLogger(__name__)

Mode = Literal["raw", "serious", "chat"]


class Meridian:
    """
    Meridian knowledge base client.

    Args:
        chroma_path:     Path to ChromaDB directory. Default: ./yc_vectors
        collection:      ChromaDB collection name. Default: transcripts
        sqlite_path:     Path to knowledge SQLite DB. Default: ./knowledge.db
        bm25_cache_path: Path to BM25 pickle cache. Default: ./bm25_cache.pkl
        gcp_project:     GCP project ID for Vertex AI.
        gcp_location:    GCP region. Default: us-central1
        gemini_model:    Gemini model ID. Default: gemini-2.0-flash
        n_results:       Number of chunks to retrieve per query. Default: 8
        wait_for_bm25:   Block init until BM25 index is ready. Default: False
    """

    def __init__(
        self,
        chroma_path: str = None,
        collection: str = None,
        sqlite_path: str = None,
        bm25_cache_path: str = None,
        gcp_project: str = None,
        gcp_location: str = None,
        gemini_model: str = None,
        n_results: int = 8,
        wait_for_bm25: bool = False,
    ):
        self._chroma_path = chroma_path or os.environ.get("CHROMA_DB_PATH", "./yc_vectors")
        self._collection = collection or os.environ.get("CHROMA_COLLECTION", "transcripts")
        self._bm25_cache = bm25_cache_path or os.environ.get("BM25_CACHE_PATH", "./bm25_cache.pkl")
        self._gcp_project = gcp_project or os.environ.get("GCP_PROJECT", "")
        self._gcp_location = gcp_location or os.environ.get("GCP_LOCATION", "us-central1")
        self._gemini_model = gemini_model or os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")
        self._n_results = n_results

        _init_search(
            chroma_path=self._chroma_path,
            collection_name=self._collection,
            bm25_cache_path=self._bm25_cache,
            wait_for_bm25=wait_for_bm25,
        )

    def search(
        self,
        query: str,
        mode: Mode = "chat",
        verbose: bool = False,
        show_sources: bool = False,
    ) -> str | list[dict] | dict:
        """
        Search the knowledge base.

        Args:
            query:        Natural language question or topic.
            mode:
                "raw"     — returns list[dict] of chunks directly from the search engine.
                            No LLM. Each dict: {chunk_id, title, text, timestamp_str,
                            timestamp_url, start_time, score}
                "serious" — LLM-synthesized answer, terse and direct. No filler.
                "chat"    — LLM-synthesized answer, natural conversational tone.
            verbose:      Print typo corrections, query variants, and progress steps.
            show_sources: If True, returns dict {"answer": str, "sources": {SRC_N: {title, url}}}
                          instead of a plain string. Sources only include chunks actually cited.
                          Default False — plain answer string with no [SRC_N] markers.

        Returns:
            list[dict]  if mode="raw"
            str         if mode="serious"/"chat" and show_sources=False
            dict        if mode="serious"/"chat" and show_sources=True
        """
        if mode == "raw":
            if verbose:
                print(f"[raw] searching: '{query}'")
            return hybrid_search(query, n_results=self._n_results)

        # ── Query expansion ───────────────────────────────────
        if verbose:
            print(f"[1/3] Expanding query: '{query}' ...")

        variants, typo_fix = expand_query(
            query,
            project=self._gcp_project,
            location=self._gcp_location,
            model=self._gemini_model,
        )

        if verbose:
            if typo_fix:
                print(f"      Typo corrected: '{query}' → '{typo_fix}'")
            print(f"      Variants ({len(variants)}):")
            for v in variants:
                print(f"        • {v}")

        # ── Multi-query search ────────────────────────────────
        if verbose:
            print(f"[2/3] Searching {len(variants)} variant(s) ...")

        seen: set[str] = set()
        all_chunks: list[dict] = []
        for i, variant in enumerate(variants):
            if verbose:
                print(f"      [{i+1}/{len(variants)}] '{variant}'")
            for chunk in hybrid_search(variant, n_results=self._n_results):
                if chunk["chunk_id"] not in seen:
                    seen.add(chunk["chunk_id"])
                    all_chunks.append(chunk)

        all_chunks.sort(key=lambda c: c["score"], reverse=True)
        top_chunks = all_chunks[:self._n_results]

        if verbose:
            print(f"      {len(top_chunks)} unique chunks after dedup")
            print(f"[3/3] Synthesizing ({mode} mode) ...")

        # ── LLM synthesis ─────────────────────────────────────
        raw_answer = synthesize(
            query=query,
            chunks=top_chunks,
            style=mode,
            project=self._gcp_project,
            location=self._gcp_location,
            model=self._gemini_model,
        )

        # Strip [SRC_N] markers from displayed answer
        clean_answer = re.sub(r'\s*\[SRC_\d+\]', '', raw_answer).strip()

        if not show_sources:
            return clean_answer

        # Build sources dict — only chunks that were actually cited
        cited_nums = set(re.findall(r'\[SRC_(\d+)\]', raw_answer))
        sources = {
            f"SRC_{i+1}": {"title": c["title"], "url": c["timestamp_url"]}
            for i, c in enumerate(top_chunks)
            if str(i + 1) in cited_nums
        }

        return {"answer": clean_answer, "sources": sources}
