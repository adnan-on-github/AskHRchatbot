"""Shared pytest fixtures for AskHR tests."""
from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from unittest.mock import MagicMock, AsyncMock, patch

from app.main import app
from app.services.rag_service import RAGService


@pytest.fixture(scope="session")
def mock_rag_service():
    """Return a fully mocked RAGService."""
    svc = MagicMock(spec=RAGService)

    async def fake_chat(session_id: str, message: str):
        from langchain_core.documents import Document
        doc = Document(
            page_content="Employees are entitled to 20 days of annual leave.",
            metadata={"source": "leave_policy.pdf", "page": 1},
        )
        return "You are entitled to 20 days of annual leave per year.", [doc]

    async def fake_stream(session_id: str, message: str):
        import json
        tokens = ["You are entitled to ", "20 days ", "of annual leave."]
        for t in tokens:
            yield t
        sources = [{"source": "leave_policy.pdf", "page": 1, "content_preview": "20 days annual leave"}]
        yield f"\n__SOURCES__{json.dumps(sources)}"

    svc.chat = AsyncMock(side_effect=fake_chat)
    svc.stream_chat = fake_stream
    svc.clear_session = MagicMock()
    return svc


@pytest_asyncio.fixture()
async def client(mock_rag_service):
    """Async test client with RAGService mocked out."""
    with patch("app.api.routes.chat.get_rag_service", return_value=mock_rag_service):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as c:
            yield c
