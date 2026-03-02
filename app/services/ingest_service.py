from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

from langchain_community.document_loaders import (
    PyPDFLoader,
    Docx2txtLoader,
    WebBaseLoader,
)
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_chroma import Chroma
from loguru import logger

from app.core.config import get_settings
from app.services.rag_service import build_embeddings

if TYPE_CHECKING:
    from langchain_core.documents import Document


class IngestService:
    """Loads HR documents (PDF, DOCX, URLs), splits them into chunks,
    embeds and stores in ChromaDB (respects EMBEDDING_PROVIDER setting)."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self.embeddings = build_embeddings(self.settings)
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.settings.chunk_size,
            chunk_overlap=self.settings.chunk_overlap,
            separators=["\n\n", "\n", ".", " ", ""],
        )

    # ------------------------------------------------------------------ #
    # Public                                                               #
    # ------------------------------------------------------------------ #

    def run(
        self,
        extra_urls: list[str] | None = None,
        reindex: bool = False,
    ) -> int:
        """Entry point.  Returns the number of chunks added."""
        logger.info("Ingest started | reindex={}", reindex)

        raw_docs = self._load_all(extra_urls)
        if not raw_docs:
            logger.warning("No documents found — aborting ingest.")
            return 0

        chunks = self.splitter.split_documents(raw_docs)
        logger.info("Split into {} chunks", len(chunks))

        self._store(chunks, reindex=reindex)
        logger.info("Ingest complete | chunks_added={}", len(chunks))
        return len(chunks)

    # ------------------------------------------------------------------ #
    # Private helpers                                                      #
    # ------------------------------------------------------------------ #

    def _load_all(self, extra_urls: list[str] | None) -> list[Document]:
        docs: list[Document] = []
        docs.extend(self._load_local_files())
        docs.extend(self._load_urls(extra_urls))
        logger.info("Loaded {} raw document pages/sections", len(docs))
        return docs

    def _load_local_files(self) -> list[Document]:
        docs: list[Document] = []
        docs_dir = Path(self.settings.documents_dir)

        if not docs_dir.exists():
            logger.warning("Documents directory not found: {}", docs_dir)
            return docs

        for fpath in docs_dir.iterdir():
            try:
                if fpath.suffix.lower() == ".pdf":
                    loader = PyPDFLoader(str(fpath))
                    loaded = loader.load()
                    for doc in loaded:
                        doc.metadata.setdefault("source", fpath.name)
                    docs.extend(loaded)
                    logger.debug("Loaded PDF: {} ({} pages)", fpath.name, len(loaded))

                elif fpath.suffix.lower() in {".docx", ".doc"}:
                    loader = Docx2txtLoader(str(fpath))
                    loaded = loader.load()
                    for doc in loaded:
                        doc.metadata.setdefault("source", fpath.name)
                    docs.extend(loaded)
                    logger.debug("Loaded DOCX: {}", fpath.name)

                else:
                    logger.debug("Skipping unsupported file type: {}", fpath.name)

            except Exception as exc:  # noqa: BLE001
                logger.error("Failed to load {}: {}", fpath.name, exc)

        return docs

    def _load_urls(self, extra_urls: list[str] | None) -> list[Document]:
        docs: list[Document] = []
        urls: list[str] = list(extra_urls or [])

        web_file = Path(self.settings.web_sources_file)
        if web_file.exists():
            file_urls = [
                line.strip()
                for line in web_file.read_text().splitlines()
                if line.strip() and not line.startswith("#")
            ]
            urls = list(set(urls + file_urls))

        if not urls:
            return docs

        logger.info("Loading {} URLs", len(urls))
        for url in urls:
            try:
                loader = WebBaseLoader(url)
                loaded = loader.load()
                for doc in loaded:
                    doc.metadata.setdefault("source", url)
                docs.extend(loaded)
                logger.debug("Loaded URL: {}", url)
            except Exception as exc:  # noqa: BLE001
                logger.error("Failed to load URL {}: {}", url, exc)

        return docs

    def _store(self, chunks: list[Document], reindex: bool) -> None:
        collection_name = self.settings.chroma_collection_name
        persist_dir = self.settings.chroma_persist_dir

        if reindex:
            logger.warning("reindex=True — wiping collection '{}'", collection_name)
            from app.db.chroma_client import get_chroma_client

            client = get_chroma_client()
            try:
                client.delete_collection(collection_name)
                logger.info("Deleted existing collection: {}", collection_name)
            except Exception:  # noqa: BLE001
                pass

        Chroma.from_documents(
            documents=chunks,
            embedding=self.embeddings,
            collection_name=collection_name,
            persist_directory=persist_dir,
        )
