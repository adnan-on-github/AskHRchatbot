from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # OpenAI
    openai_api_key: str = ""

    # ChromaDB
    chroma_persist_dir: str = "./chroma_db"
    chroma_collection_name: str = "askhr_docs"

    # RAG tuning
    chunk_size: int = 1000
    chunk_overlap: int = 200
    retriever_k: int = 5
    llm_model: str = "gpt-4o"
    llm_temperature: float = 0.2
    embedding_model: str = "text-embedding-3-small"

    # Server
    log_level: str = "INFO"
    allowed_origins: str = "*"
    rate_limit: str = "20/minute"

    # Data paths
    documents_dir: str = "./data/documents"
    web_sources_file: str = "./data/web_sources.txt"

    # Memory window
    memory_window: int = 10


@lru_cache
def get_settings() -> Settings:
    return Settings()
