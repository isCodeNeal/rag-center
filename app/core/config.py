"""Application configuration.

All tunables (model endpoint, vector store, chunking params) are loaded from the
environment / .env so nothing model- or store-specific is hard-coded in business code.
"""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ----- Application -----
    app_env: str = "local"
    app_name: str = "rag-center"

    # ----- Logging -----
    log_level: str = "INFO"
    log_dir: str = "logs"
    log_to_file: bool = True
    log_max_bytes: int = 10 * 1024 * 1024  # 单个日志文件 10MB 后滚动
    log_backup_count: int = 10  # 最多保留 10 个历史文件
    log_request_body: bool = True  # 是否记录请求/响应体（生产可关闭以降噪/脱敏）

    # ----- Database -----
    database_url: str = (
        "postgresql+psycopg://postgres:postgres@localhost:5432/rag_center"
    )

    # ----- Embedding provider (OpenAI-compatible) -----
    model_base_url: str = "https://api.openai.com/v1"
    model_api_key: str = "your-api-key"
    embedding_model: str = "text-embedding-3-small"
    embedding_dim: int = 1536

    # ----- Vector store -----
    vector_store: str = "pgvector"

    # ----- Chunking / retrieval -----
    chunk_size: int = 800
    chunk_overlap: int = 100
    top_k: int = 5

    @property
    def async_database_url(self) -> str:
        """URL used by the async SQLAlchemy engine.

        `postgresql+psycopg` (psycopg3) works for both sync (Alembic) and async
        (create_async_engine) engines, so no rewriting is required.
        """
        return self.database_url


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
