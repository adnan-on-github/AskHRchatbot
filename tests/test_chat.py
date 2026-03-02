"""Tests for the /api/v1/chat endpoints."""
from __future__ import annotations

import json
import pytest


@pytest.mark.asyncio
async def test_health(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_chat_sync_returns_answer(client):
    payload = {"session_id": "test-session-1", "message": "How many leave days do I get?"}
    resp = await client.post("/api/v1/chat/sync", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert "answer" in body
    assert len(body["answer"]) > 0
    assert "sources" in body
    assert isinstance(body["sources"], list)


@pytest.mark.asyncio
async def test_chat_sync_has_source_fields(client):
    payload = {"session_id": "test-session-2", "message": "What is the leave policy?"}
    resp = await client.post("/api/v1/chat/sync", json=payload)
    assert resp.status_code == 200
    sources = resp.json()["sources"]
    if sources:
        src = sources[0]
        assert "source" in src
        assert "content_preview" in src


@pytest.mark.asyncio
async def test_chat_stream_delivers_tokens(client):
    payload = {"session_id": "test-session-3", "message": "Tell me about HR leave policy."}
    async with client.stream("POST", "/api/v1/chat", json=payload) as resp:
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers.get("content-type", "")

        full_content = await resp.aread()
        text = full_content.decode()
        assert "data:" in text


@pytest.mark.asyncio
async def test_clear_session(client):
    resp = await client.delete("/api/v1/chat/test-session-clear")
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_chat_requires_message(client):
    resp = await client.post("/api/v1/chat/sync", json={"session_id": "s", "message": ""})
    assert resp.status_code == 422  # Pydantic min_length validation
