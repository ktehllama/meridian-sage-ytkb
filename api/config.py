# All env var reads happen here. Other modules import `config` and read attributes off it.

import os
from dataclasses import dataclass


@dataclass
class Config:
    CHROMA_DB_PATH: str
    CHROMA_COLLECTION: str
    SQLITE_DB_PATH: str
    GCP_PROJECT: str
    GCP_LOCATION: str
    GEMINI_MODEL: str
    BM25_CACHE_PATH: str
    LLM_PROVIDER: str  # "gemini" | future: "anthropic", "openai", ...
    CHATS_DB_PATH: str


def _load() -> Config:
    return Config(
        CHROMA_DB_PATH=os.environ.get("CHROMA_DB_PATH", "./yc_vectors"),
        CHROMA_COLLECTION=os.environ.get("CHROMA_COLLECTION", "transcripts"),
        SQLITE_DB_PATH=os.environ.get("SQLITE_DB_PATH", "./knowledge.db"),
        GCP_PROJECT=os.environ.get("GCP_PROJECT", ""),
        GCP_LOCATION=os.environ.get("GCP_LOCATION", "us-central1"),
        GEMINI_MODEL=os.environ.get("GEMINI_MODEL", "gemini-2.0-flash"),
        BM25_CACHE_PATH=os.environ.get("BM25_CACHE_PATH", "./bm25_cache.pkl"),
        LLM_PROVIDER=os.environ.get("LLM_PROVIDER", "gemini"),
        CHATS_DB_PATH=os.environ.get("CHATS_DB_PATH", "./chats.db"),
    )


config: Config = _load()
