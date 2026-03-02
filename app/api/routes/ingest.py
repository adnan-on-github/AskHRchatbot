from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, HTTPException, status, UploadFile, File
from loguru import logger
from pathlib import Path

from app.models.schemas import IngestRequest, IngestResponse
from app.services.ingest_service import IngestService
from app.core.config import get_settings

router = APIRouter(prefix="/ingest", tags=["Ingest"])


def _run_ingest(urls: list[str] | None, reindex: bool) -> None:
    """Synchronous wrapper executed inside BackgroundTasks."""
    try:
        service = IngestService()
        count = service.run(extra_urls=urls, reindex=reindex)
        logger.info("Background ingest finished | chunks_added={}", count)
    except Exception as exc:
        logger.exception("Background ingest failed: {}", exc)


@router.post(
    "",
    summary="Trigger HR document ingestion",
    response_model=IngestResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def ingest(
    request: IngestRequest,
    background_tasks: BackgroundTasks,
) -> IngestResponse:
    """
    Triggers an asynchronous ingestion pipeline:

    1. Loads PDFs and DOCX files from `data/documents/`.
    2. Crawls URLs from `data/web_sources.txt` (plus any in the request body).
    3. Splits, embeds, and stores chunks in ChromaDB.

    Returns **202 Accepted** immediately. Check server logs for progress.
    Set `reindex=true` to wipe and rebuild the entire collection.
    """
    logger.info(
        "POST /ingest | reindex={} extra_urls={}",
        request.reindex,
        len(request.urls or []),
    )
    background_tasks.add_task(_run_ingest, request.urls, request.reindex)
    return IngestResponse(
        status="accepted",
        message="Ingestion started in the background. Check logs for progress.",
    )


@router.post(
    "/upload",
    summary="Upload and ingest a document file",
    response_model=IngestResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def upload_and_ingest(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(..., description="PDF or DOCX file to ingest"),
) -> IngestResponse:
    """Upload a single PDF or DOCX file directly and trigger ingestion."""
    settings = get_settings()
    docs_dir = Path(settings.documents_dir)
    docs_dir.mkdir(parents=True, exist_ok=True)

    allowed_extensions = {".pdf", ".docx", ".doc"}
    fpath = Path(file.filename or "upload")
    if fpath.suffix.lower() not in allowed_extensions:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported file type '{fpath.suffix}'. Allowed: PDF, DOCX.",
        )

    save_path = docs_dir / fpath.name
    content = await file.read()
    save_path.write_bytes(content)
    logger.info("Uploaded file saved: {}", save_path)

    background_tasks.add_task(_run_ingest, None, False)
    return IngestResponse(
        status="accepted",
        message=f"File '{file.filename}' uploaded and ingestion started.",
    )
