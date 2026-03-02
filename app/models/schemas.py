from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field
import uuid


class ChatRequest(BaseModel):
    session_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Unique session ID for multi-turn conversation tracking.",
    )
    message: str = Field(..., min_length=1, max_length=4096, description="User's HR question.")
    provider: Literal["openai", "huggingface"] = Field(
        default="openai",
        description="LLM provider to use for this request.",
    )
    hf_access_mode: Literal["api", "local"] = Field(
        default="api",
        description="HuggingFace access mode: 'api' for Inference API, 'local' to load weights.",
    )


class SourceDocument(BaseModel):
    source: str
    page: int | None = None
    content_preview: str


class ChatResponse(BaseModel):
    session_id: str
    answer: str
    sources: list[SourceDocument]


class IngestRequest(BaseModel):
    urls: list[str] | None = Field(
        default=None,
        description="Optional list of URLs to ingest. Falls back to web_sources.txt if not provided.",
    )
    reindex: bool = Field(
        default=False,
        description="If True, wipes the existing collection and rebuilds from scratch.",
    )


class IngestResponse(BaseModel):
    status: str
    message: str


class HealthResponse(BaseModel):
    status: str
    version: str = "1.0.0"
