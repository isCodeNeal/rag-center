"""基于 LLMProvider 的大模型打分重排实现。

流程：
    候选 chunk（向量召回结果）
    -> 截断候选数量 / 截断单个 chunk 的 content 长度
    -> 组装结构化 JSON（query + candidates + top_n）
    -> LLMProvider.chat_json(system_prompt, user_payload)
    -> 用 LLMRerankResponse 校验/解析大模型返回的 rankings
    -> 按 chunk_id 把 rerank_score 合并回候选 chunk
    -> 按 rerank_score 降序排序，截断到 top_n

`LLMRerankProvider` 不直接发 HTTP 请求，也不直接依赖 DeepSeek/百炼等具体厂商，
只通过注入的 `LLMProvider.chat_json()` 访问大模型。调用失败或返回内容解析失败时
统一抛出 `RerankError`，由上层（RagService）决定如何降级为原始向量排序。
"""
from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from app.core.config import settings
from app.core.exceptions import LLMProviderError, RerankError
from app.core.logging import get_logger
from app.providers.llm.base import LLMProvider
from app.providers.rerank.base import RerankProvider
from app.schemas.rerank import LLMRerankResponse

logger = get_logger(__name__)

LLM_RERANK_PROVIDER_NAME = "llm"

_SYSTEM_PROMPT = """你是 RAG 检索重排器。你的任务是根据用户问题，对候选知识片段进行相关性打分和排序。

要求：
1. 只判断候选片段是否有助于回答用户问题。
2. 不要回答用户问题。
3. 不要编造候选片段中不存在的信息。
4. 每个候选片段给出 0 到 1 之间的 rerank_score。
5. 分数越高表示越相关、越适合作为 RAG 上下文。
6. 只返回 JSON，不要返回 Markdown，不要返回解释性文字。

返回格式必须是严格 JSON：
{"rankings": [{"chunk_id": "...", "rerank_score": 0.0, "reason": "..."}]}"""


class LLMRerankProvider(RerankProvider):
    def __init__(
        self,
        llm_provider: LLMProvider,
        *,
        max_candidates: int | None = None,
        chunk_max_chars: int | None = None,
        temperature: float | None = None,
    ):
        self._llm = llm_provider
        self._max_candidates = max_candidates or settings.rerank_max_candidates
        self._chunk_max_chars = chunk_max_chars or settings.rerank_chunk_max_chars
        self._temperature = temperature if temperature is not None else settings.rerank_temperature

    @property
    def name(self) -> str:
        return LLM_RERANK_PROVIDER_NAME

    async def rerank(
        self,
        *,
        query: str,
        chunks: list[dict[str, Any]],
        top_n: int,
    ) -> list[dict[str, Any]]:
        if not chunks:
            return []

        # 1. 截断候选数量，控制送入大模型的 token 成本。
        candidates = chunks[: self._max_candidates]

        # 2. 组装结构化 JSON 输入（不传 embedding 向量、不传数据库内部无关字段）。
        user_payload = {
            "query": query,
            "candidates": [
                {
                    "chunk_id": c["chunk_id"],
                    "document_id": c["document_id"],
                    "title": c["title"],
                    "content": _truncate(c["content"], self._chunk_max_chars),
                    "vector_score": c.get("score"),
                }
                for c in candidates
            ],
            "top_n": top_n,
        }

        # 3. 调用大模型打分（仅通过 LLMProvider，不直接发 HTTP 请求）。
        try:
            raw_result = await self._llm.chat_json(
                system_prompt=_SYSTEM_PROMPT,
                user_payload=user_payload,
                temperature=self._temperature,
            )
        except LLMProviderError as exc:
            raise RerankError(f"llm rerank call failed: {exc.detail or exc.msg}")

        # 4. 校验/解析大模型返回的 rankings；解析失败也归类为可降级的 RerankError。
        try:
            parsed = LLMRerankResponse.model_validate(raw_result)
        except ValidationError as exc:
            raise RerankError(f"llm rerank response schema invalid: {exc}")

        # chunk_id -> rerank_score/reason，只保留候选集合内的合法 chunk_id，
        # 大模型返回了不存在的 chunk_id 时直接忽略。
        candidate_ids = {c["chunk_id"] for c in candidates}
        score_map: dict[str, tuple[float, str | None]] = {}
        for ranking in parsed.rankings:
            if ranking.chunk_id not in candidate_ids:
                logger.warning("RERANK_UNKNOWN_CHUNK_ID | chunk_id=%s", ranking.chunk_id)
                continue
            score_map[ranking.chunk_id] = (ranking.rerank_score, ranking.reason)

        # 5. 合并回候选 chunk：漏打分的 chunk 默认 rerank_score=0；保留原始字段。
        reranked = []
        for c in candidates:
            score, reason = score_map.get(c["chunk_id"], (0.0, None))
            item = dict(c)
            item["rerank_score"] = score
            if reason is not None:
                # rerank_reason 只用于日志/调试，不默认暴露给业务接口响应结构。
                item["rerank_reason"] = reason
            reranked.append(item)

        # 6. 按 rerank_score 降序排序，截断到 top_n。
        reranked.sort(key=lambda c: c["rerank_score"], reverse=True)
        return reranked[:top_n]


def _truncate(text: str, max_chars: int) -> str:
    text = text or ""
    if len(text) <= max_chars:
        return text
    return text[:max_chars]
