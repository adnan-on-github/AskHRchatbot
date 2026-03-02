from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Provider selection  ("openai" | "huggingface")
    llm_provider: str = "openai"          # startup default shown in sidebar
    embedding_provider: str = "openai"    # controls which embeddings go into ChromaDB

    # OpenAI
    openai_api_key: str = ""

    # HuggingFace
    hf_api_token: str = ""                # HuggingFace Hub token (Inference API)
    hf_llm_model: str = "meta-llama/Llama-3-8B-Instruct"  # default HF chat model
    hf_embedding_model: str = "BAAI/bge-small-en-v1.5"    # default HF embedding model
    hf_access_mode: str = "api"           # "api" (Inference API) | "local" (load weights)

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
