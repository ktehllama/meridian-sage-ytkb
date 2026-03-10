"""
api/main.py
===========
FastAPI application — route handlers, CORS, lifespan startup.

Start the server:
    cd /path/to/yt_scraper_consultant
    uvicorn api.main:app --reload --port 8000

Or with explicit env vars:
    CHROMA_DB_PATH=./yc_vectors SQLITE_DB_PATH=./knowledge.db uvicorn api.main:app --port 8000
"""

import logging
import re
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from api import search as search_module
from api import gemini as gemini_module
from api import websearch as websearch_module
from api.models import (
    ChatRequest,
    ChatResponse,
    ChannelItem,
    ChannelListResponse,
    HealthResponse,
    RandomFactResponse,
    Source,
    UsageInfo,
    VideoItem,
    VideoListResponse,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────
# Lifespan — startup/shutdown
# ─────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialise search engine on startup. Fail fast if ChromaDB is unreachable."""
    logger.info("Sage Chat API starting up ...")
    try:
        search_module.init_search()
        logger.info("Search engine ready.")
    except RuntimeError as e:
        logger.error(f"STARTUP FAILED: {e}")
        # Allow startup to complete so /api/health can report 'degraded'
    yield
    logger.info("Sage Chat API shutting down.")


# ─────────────────────────────────────────────────────────────
# App + CORS
# ─────────────────────────────────────────────────────────────

app = FastAPI(
    title="Sage Chat API",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:3001",
    ],
    allow_origin_regex=r"https://.*\.vercel\.app|http://.*\.local:\d+|http://.*\.lan:\d+|http://192\.168\.\d+\.\d+:\d+|http://10\.\d+\.\d+\.\d+:\d+|http://172\.(1[6-9]|2\d|3[01])\.\d+\.\d+:\d+",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request as StarletteRequest

class PrivateNetworkMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: StarletteRequest, call_next):
        response = await call_next(request)
        response.headers["Access-Control-Allow-Private-Network"] = "true"
        return response

app.add_middleware(PrivateNetworkMiddleware)


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────

_SRC_ID_RE = re.compile(r"\[SRC_(\d+)\]")


def _build_sources(chunks: list[dict]) -> list[Source]:
    """Convert search result dicts to Source Pydantic models."""
    sources = []
    for i, chunk in enumerate(chunks):
        text = chunk.get("text", "")
        quote = text[:150].rstrip() + ("..." if len(text) > 150 else "")
        sources.append(
            Source(
                src_id=f"SRC_{i + 1}",
                title=chunk.get("title", "Unknown"),
                timestamp_str=chunk.get("timestamp_str", "0:00"),
                url=chunk.get("timestamp_url", ""),
                quote=quote,
            )
        )
    return sources


def _deduplicate_chunks(results_by_variant: list[list[dict]]) -> list[dict]:
    """
    Merge search results from multiple query variants.
    Deduplicate by chunk_id, keeping the highest score for each chunk.
    Returns list sorted by score descending.
    """
    best: dict[str, dict] = {}
    for results in results_by_variant:
        for chunk in results:
            cid = chunk["chunk_id"]
            if cid not in best or chunk["score"] > best[cid]["score"]:
                best[cid] = chunk
    return sorted(best.values(), key=lambda c: c["score"], reverse=True)


# ─────────────────────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────────────────────

@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    """
    Main chat endpoint.
    Pipeline: query expansion → hybrid search (per variant) → deduplicate → synthesize.
    """
    if search_module.get_collection() is None:
        raise HTTPException(
            status_code=503,
            detail="Knowledge base unavailable. Check server logs for ChromaDB errors.",
        )

    # Step 1: Expand query into paraphrase variants
    query_variants = gemini_module.expand_query(request.query)
    logger.info(f"Query variants ({len(query_variants)}): {query_variants}")

    # Step 2: Search all variants, collect results
    all_results: list[list[dict]] = []
    for variant in query_variants:
        variant_results = search_module.hybrid_search(variant, n_results=20)
        all_results.append(variant_results)

    # Step 3: Deduplicate and take top 8
    merged = _deduplicate_chunks(all_results)
    top_chunks = merged[:8]
    logger.info(f"Retrieved {len(merged)} unique chunks, using top {len(top_chunks)}")

    # Step 3b: Web search fallback — if no KB results above confidence threshold
    best_score = top_chunks[0]["score"] if top_chunks else 0.0
    if best_score < 0.30:
        logger.info(f"KB best score {best_score:.3f} < 0.30 — falling back to web search")
        web_results = websearch_module.web_search(request.query, n=4)
        if web_results:
            top_chunks = web_results

    # Step 4: Synthesize answer
    answer, raw_usage = gemini_module.synthesize(
        query=request.query,
        chunks=top_chunks,
        history=request.history if request.mode == "conversation" else [],
        mode=request.mode,
    )

    # Step 5: Build source list (one per chunk, in [SRC_N] order)
    sources = _build_sources(top_chunks)

    usage_obj = None
    if raw_usage:
        usage_obj = UsageInfo(
            prompt_tokens=raw_usage["prompt_tokens"],
            completion_tokens=raw_usage["completion_tokens"],
        )

    return ChatResponse(
        answer=answer,
        sources=sources,
        mode=request.mode,
        usage=usage_obj,
    )


@app.get("/api/videos", response_model=VideoListResponse)
async def get_videos(
    channel: str = Query(default="", description="Filter by channel handle (partial match)"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> VideoListResponse:
    """List videos in the knowledge base, optionally filtered by channel."""
    channel_filter = channel.strip() if channel else None
    videos_raw, total = search_module.list_videos(
        channel=channel_filter,
        limit=limit,
        offset=offset,
    )
    videos = [VideoItem(**v) for v in videos_raw]
    return VideoListResponse(videos=videos, total=total)


@app.get("/api/channels", response_model=ChannelListResponse)
async def get_channels() -> ChannelListResponse:
    """List all channels in the knowledge base with their video counts."""
    channels_raw = search_module.list_channels()
    channels = [ChannelItem(**c) for c in channels_raw]
    return ChannelListResponse(channels=channels)


@app.get("/api/random-fact", response_model=RandomFactResponse)
async def random_fact() -> RandomFactResponse:
    """Return a random transcript excerpt to display on the homescreen."""
    fact = search_module.get_random_fact()
    if fact is None:
        raise HTTPException(status_code=503, detail="Knowledge base unavailable.")
    return RandomFactResponse(**fact)


@app.get("/api/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Health check — reports ChromaDB and SQLite state."""
    collection = search_module.get_collection()
    if collection is None:
        return HealthResponse(
            status="degraded",
            chroma_chunks=0,
            db_videos=search_module.get_db_video_count(),
        )
    return HealthResponse(
        status="ok",
        chroma_chunks=search_module.get_chunk_count(),
        db_videos=search_module.get_db_video_count(),
    )
