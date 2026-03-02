import chromadb
from chromadb import PersistentClient
from functools import lru_cache
from app.core.config import get_settings
from loguru import logger


@lru_cache(maxsize=1)
def get_chroma_client() -> PersistentClient:
    settings = get_settings()
    logger.info(
        "Initialising ChromaDB persistent client at path={}",
        settings.chroma_persist_dir,
    )
    client = chromadb.PersistentClient(path=settings.chroma_persist_dir)
    return client
