"""重排（rerank）相关 schemas。

覆盖三类数据：
1. `RerankOptions` —— /api/v1/rag/retrieve 请求体中可选的单次请求级配置。
2. `LLMRerankRanking` / `LLMRerankResponse` —— 大模型返回的打分 JSON 的校验模型，
   用于在 `LLMRerankProvider` 内部安全解析，而不是盲目信任大模型输出的结构。
3. `RerankMetadata` —— 返回给业务方的 rerank 元信息，嵌入响应 `metadata.rerank`。

注意：候选 chunk 和重排结果在 provider 内部仍以 `list[dict]` 形式传递（与
`VectorStore` 的既有风格保持一致），这里的 schema 只负责「大模型返回内容」和
「对外响应」两处需要强校验的边界。
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class RerankOptions(BaseModel):
    """请求体中可选的 rerank_options，用于单次请求覆盖 .env 里的全局配置。"""

    enabled: bool | None = Field(default=None, description="是否启用大模型重排；不传则使用系统配置")
    top_n: int | None = Field(default=None, ge=1, le=50, description="重排后最终返回数量；不传则使用系统配置")


class LLMRerankRanking(BaseModel):
    """大模型返回的 rankings 数组中的单条打分结果。"""

    chunk_id: str
    rerank_score: float = Field(..., ge=0.0, le=1.0)
    # 打分原因，仅用于日志/调试，不会默认暴露给业务接口。
    reason: str | None = None


class LLMRerankResponse(BaseModel):
    """大模型必须返回的严格 JSON 结构：{"rankings": [...]}。"""

    rankings: list[LLMRerankRanking] = Field(default_factory=list)


class RerankMetadata(BaseModel):
    """返回给业务方的 rerank 元信息，嵌入 RetrieveMetadata.rerank。"""

    enabled: bool
    provider: str | None = None
    llm_provider: str | None = None
    model: str | None = None
    top_n: int | None = None
    candidate_count: int | None = None
    # 大模型重排失败、自动降级为原向量排序时置为 True。
    degraded: bool = False
    error: str | None = None
