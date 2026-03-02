"""Tests for the /api/v1/ingest endpoints."""
from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock
from httpx import AsyncClient, ASGITransport

from app.main import app


@pytest.mark.asyncio
async def test_ingest_returns_202():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        with patch("app.api.routes.ingest._run_ingest") as mock_run:
            resp = await client.post(
                "/api/v1/ingest",
                json={"reindex": False},
            )
    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] == "accepted"
    assert "message" in body


@pytest.mark.asyncio
async def test_ingest_with_reindex():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        with patch("app.api.routes.ingest._run_ingest"):
            resp = await client.post(
                "/api/v1/ingest",
                json={"reindex": True, "urls": ["https://example.com/hr-policy"]},
            )
    assert resp.status_code == 202


@pytest.mark.asyncio
async def test_upload_rejects_invalid_extension():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/api/v1/ingest/upload",
            files={"file": ("malware.exe", b"binary content", "application/octet-stream")},
        )
    assert resp.status_code == 415
