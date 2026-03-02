from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── OpenAI (standard) ────────────────────────────────────────────────
    # Used for local development. Leave empty when using Managed Identity.
    openai_api_key: str = ""

    # ── Azure OpenAI ─────────────────────────────────────────────────────
    # Set USE_MANAGED_IDENTITY=true in Azure to use keyless auth.
    use_managed_identity: bool = False
    azure_openai_endpoint: str = ""
    azure_openai_api_key: str = ""          # only needed if NOT using MI
    azure_openai_api_version: str = "2024-02-01"
    azure_openai_chat_deployment: str = "gpt-4o"
    azure_openai_embedding_deployment: str = "text-embedding-3-small"

    # ── ChromaDB ─────────────────────────────────────────────────────────
    chroma_persist_dir: str = "./chroma_db"
    chroma_collection_name: str = "askhr_docs"

    # ── RAG tuning ───────────────────────────────────────────────────────
    chunk_size: int = 1000
    chunk_overlap: int = 200
    retriever_k: int = 5
    llm_model: str = "gpt-4o"              # used only for non-Azure path
    llm_temperature: float = 0.2
    embedding_model: str = "text-embedding-3-small"  # non-Azure path

    # ── Server ───────────────────────────────────────────────────────────
    log_level: str = "INFO"
    allowed_origins: str = "*"
    rate_limit: str = "20/minute"

    # ── Data paths ───────────────────────────────────────────────────────
    documents_dir: str = "./data/documents"
    web_sources_file: str = "./data/web_sources.txt"

    # ── Memory ───────────────────────────────────────────────────────────
    memory_window: int = 10

    @property
    def is_azure(self) -> bool:
        """True when Azure OpenAI endpoint is configured."""
        return bool(self.azure_openai_endpoint)


@lru_cache
def get_settings() -> Settings:
    return Settings()
