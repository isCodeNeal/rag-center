"""应用配置。

所有可调参数（模型端点、向量库、分块参数）均从环境变量 / .env 加载，
业务代码中不硬编码任何与具体模型或存储相关的内容。
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

    # ----- 应用 -----
    app_env: str = "local"
    app_name: str = "rag-center"

    # ----- 日志 -----
    log_level: str = "INFO"
    log_dir: str = "logs"
    log_to_file: bool = True
    log_max_bytes: int = 10 * 1024 * 1024  # 单个日志文件 10MB 后滚动
    log_backup_count: int = 10  # 最多保留 10 个历史文件
    log_request_body: bool = True  # 是否记录请求/响应体（生产可关闭以降噪/脱敏）

    # ----- 数据库 -----
    database_url: str = (
        "postgresql+psycopg://postgres:postgres@localhost:5432/rag_center"
    )

    # ----- Embedding 提供方（OpenAI 兼容）-----
    model_base_url: str = "https://api.openai.com/v1"
    model_api_key: str = "your-api-key"
    embedding_model: str = "text-embedding-3-small"
    embedding_dim: int = 1536

    # ----- 向量库 -----
    vector_store: str = "pgvector"

    # ----- 分块 / 检索 -----
    chunk_size: int = 800
    chunk_overlap: int = 100
    top_k: int = 5

    @property
    def async_database_url(self) -> str:
        """异步 SQLAlchemy engine 使用的 URL。

        `postgresql+psycopg`（psycopg3）同时适用于同步（Alembic）和异步
        （create_async_engine）engine，因此无需做任何转换。
        """
        return self.database_url


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
