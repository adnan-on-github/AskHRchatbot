from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from loguru import logger

from app.models.schemas import ChatRequest, ChatResponse, SourceDocument
from app.services.rag_service import get_rag_service, RAGService

router = APIRouter(prefix="/chat", tags=["Chat"])


@router.post(
    "",
    summary="Ask the HR chatbot a question",
    response_model=ChatResponse,
)
async def chat(
    request: ChatRequest,
    rag: RAGService = Depends(get_rag_service),
) -> StreamingResponse:
    """
    Send a message to AskHR.

    - Streams the answer token-by-token as Server-Sent Events (text/event-stream).
    - The final SSE event contains a JSON payload with `sources`.
    - Pass the same `session_id` across turns to maintain conversation history.
    """
    logger.info(
        "POST /chat | session={} provider={}",
        request.session_id, request.provider,
    )

    async def event_generator():
        full_answer = ""
        sources_json: str | None = None

        try:
            async for token in rag.stream_chat(
                request.session_id,
                request.message,
                provider=request.provider,
                hf_access_mode=request.hf_access_mode,
            ):
                if token.startswith("\n__SOURCES__"):
                    sources_json = token.replace("\n__SOURCES__", "")
                    break
                full_answer += token
                yield f"data: {json.dumps({'token': token})}\n\n"

            # Final event with complete answer + sources
            sources: list[dict] = json.loads(sources_json) if sources_json else []
            yield (
                f"data: {json.dumps({'done': True, 'answer': full_answer, 'sources': sources})}\n\n"
            )
            yield "data: [DONE]\n\n"

        except Exception as exc:
            logger.exception("Streaming error for session={}", request.session_id)
            yield f"data: {json.dumps({'error': str(exc)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.post(
    "/sync",
    summary="Ask the HR chatbot (non-streaming)",
    response_model=ChatResponse,
)
async def chat_sync(
    request: ChatRequest,
    rag: RAGService = Depends(get_rag_service),
) -> ChatResponse:
    """Non-streaming endpoint — returns the full answer in one JSON response."""
    logger.info(
        "POST /chat/sync | session={} provider={}",
        request.session_id, request.provider,
    )

    try:
        answer, source_docs = await rag.chat(
            request.session_id,
            request.message,
            provider=request.provider,
            hf_access_mode=request.hf_access_mode,
        )
    except Exception as exc:
        logger.exception("Chat error for session={}", request.session_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Chat processing failed: {exc}",
        ) from exc

    sources = [
        SourceDocument(
            source=doc.metadata.get("source", "unknown"),
            page=doc.metadata.get("page"),
            content_preview=doc.page_content[:200],
        )
        for doc in source_docs
    ]

    return ChatResponse(
        session_id=request.session_id,
        answer=answer,
        sources=sources,
    )


@router.delete(
    "/{session_id}",
    summary="Clear conversation history for a session",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
async def clear_session(
    session_id: str,
    rag: RAGService = Depends(get_rag_service),
) -> None:
    rag.clear_session(session_id)
