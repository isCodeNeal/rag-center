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

    # ----- 通用大模型 provider（用于 rerank、query rewrite 等能力）-----
    # llm_provider 第一版仅支持 "openai_compatible"；DeepSeek、百炼等兼容 OpenAI
    # chat completions 协议的厂商都走这个实现，只需切换 base_url / model。
    llm_provider: str = "openai_compatible"
    llm_base_url: str = "https://api.deepseek.com/v1"
    llm_api_key: str = "your-deepseek-api-key"
    llm_model: str = "deepseek-chat"
    llm_timeout_seconds: int = 60

    # ----- 重排（rerank）-----
    rerank_enabled: bool = False
    # rerank_provider 第一版支持 "llm"（通过 LLMProvider 调用大模型打分）和
    # "noop"（不重排，占位实现，用于配置关闭 rerank 或做对照测试）。
    rerank_provider: str = "llm"
    rerank_top_n: int = 5
    rerank_max_candidates: int = 20  # 最多送入大模型的候选 chunk 数，控制 token 成本
    rerank_chunk_max_chars: int = 1000  # 每个 chunk 送入大模型前的最大字符数
    rerank_temperature: float = 0.0

    # ----- 关键词检索（BM25，用于混合检索）-----
    # 第一版 provider 为 "elasticsearch"；后续可扩展 "opensearch"。
    keyword_search_provider: str = "elasticsearch"
    elasticsearch_url: str = "http://localhost:9200"
    elasticsearch_index: str = "rag_chunks"
    # index mapping 中 title/content 使用的分词器；IK 需 ES 安装 analysis-ik 插件。
    # 若环境未装 IK，可临时改为 "standard" 兜底（中文分词效果会变差）。
    elasticsearch_analyzer: str = "ik_max_word"
    elasticsearch_search_analyzer: str = "ik_smart"

    # ----- 检索模式与混合检索（RRF 融合）-----
    # retrieval_mode 默认检索模式："vector" / "bm25" / "hybrid"。
    retrieval_mode: str = "vector"
    hybrid_fusion: str = "rrf"  # 第一版融合策略仅支持 rrf
    hybrid_rrf_k: int = 60
    hybrid_vector_top_k: int = 20
    hybrid_bm25_top_k: int = 20
    hybrid_top_n: int = 20  # 融合后默认返回候选数量

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
