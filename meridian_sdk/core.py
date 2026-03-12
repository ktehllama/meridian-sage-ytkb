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
"""

import logging
import os
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

    def search(self, query: str, mode: Mode = "chat") -> str | list[dict]:
        """
        Search the knowledge base.

        Args:
            query: Natural language question or topic.
            mode:
                "raw"     — returns list[dict] of chunks directly from the search engine.
                            No LLM. Each dict: {chunk_id, title, text, timestamp_str,
                            timestamp_url, start_time, score}
                "serious" — LLM-synthesized answer, terse and direct. No filler.
                "chat"    — LLM-synthesized answer, natural conversational tone.

        Returns:
            str (serious/chat) or list[dict] (raw).
        """
        if mode == "raw":
            return hybrid_search(query, n_results=self._n_results)

        # Expand query into variants for better recall
        variants = expand_query(
            query,
            project=self._gcp_project,
            location=self._gcp_location,
            model=self._gemini_model,
        )

        # Search with each variant, merge and deduplicate
        seen: set[str] = set()
        all_chunks: list[dict] = []
        for variant in variants:
            for chunk in hybrid_search(variant, n_results=self._n_results):
                if chunk["chunk_id"] not in seen:
                    seen.add(chunk["chunk_id"])
                    all_chunks.append(chunk)

        # Re-sort merged pool by score, keep top n
        all_chunks.sort(key=lambda c: c["score"], reverse=True)
        top_chunks = all_chunks[:self._n_results]

        return synthesize(
            query=query,
            chunks=top_chunks,
            style=mode,  # "serious" or "chat"
            project=self._gcp_project,
            location=self._gcp_location,
            model=self._gemini_model,
        )
