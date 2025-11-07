"""
Application configuration powered by environment variables.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    project_name: str = "notisnu-backend"
    environment: str = "development"
    mongo_url: str = "mongodb://mongo:27017"
    mongo_db: str = "notisnu"
    qdrant_host: str = "qdrant"
    qdrant_port: int = 6333
    qdrant_collection_notices: str = "notice_vectors"
    qdrant_vector_size: int = 768
    api_port: int = 8000
    timezone: str = "Asia/Seoul"
    scheduler_enabled: bool = False
    scheduler_interval_minutes: int = 30
    llm_api_base: str | None = None
    llm_api_key: str | None = None
    llm_summary_endpoint: str = "/v1/chat/completions"
    llm_embedding_endpoint: str = "/v1/embeddings"
    llm_summary_model: str = "gpt-3.5-turbo"
    llm_embedding_model: str = "text-embedding-3-small"
    llm_summary_max_tokens: int = 120
    llm_api_timeout: float = 15.0
    crawler_sample_html: str | None = "docs/sample_pages/scholarship_board.html"
    crawler_request_timeout: float = 10.0
    board_catalog_path: str | None = "docs/board_sources/catalog.json"
    crawler_verify_ssl: bool = True

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="allow",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """
    Return a cached Settings instance so config is loaded once per process.
    """
    return Settings()
