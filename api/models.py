"""
api/models.py
=============
Pydantic models for all request and response shapes.
Single source of truth — imported by main.py, gemini.py, search.py.
"""

from typing import Literal, Optional
from pydantic import BaseModel, Field


class Message(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    mode: Literal["ephemeral", "conversation"] = "ephemeral"
    history: list[Message] = Field(default_factory=list)


class Source(BaseModel):
    src_id: str          # e.g. "SRC_1"
    title: str
    timestamp_str: str   # e.g. "12:34"
    url: str             # YouTube timestamp deep link
    quote: str           # first ~150 chars of chunk text


class UsageInfo(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0


class ChatResponse(BaseModel):
    answer: str
    sources: list[Source]
    mode: Literal["ephemeral", "conversation"]
    usage: Optional[UsageInfo] = None


class VideoItem(BaseModel):
    id: str
    title: str
    channel: str
    url: str
    duration: Optional[int] = None


class VideoListResponse(BaseModel):
    videos: list[VideoItem]
    total: int


class ChannelItem(BaseModel):
    name: str
    video_count: int


class ChannelListResponse(BaseModel):
    channels: list[ChannelItem]


class HealthResponse(BaseModel):
    status: str          # "ok" | "degraded"
    chroma_chunks: int
    db_videos: int
    model: str = ""


class StoredChatRequest(BaseModel):
    id: str
    name: str
    mode: str
    messages: list
    saved_at: int


class RenameChatRequest(BaseModel):
    name: str


class RandomFactResponse(BaseModel):
    title: str
    channel: str
    excerpt: str
    timestamp_str: str
    url: str
