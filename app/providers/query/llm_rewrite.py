"""LLM 改问法：把口语 query 改成更贴近文档表述的检索句。

复用现有 LLMProvider，不新增模型配置。只传用户原话 + kb 名称 + 领域说明，
不读文档正文以避免 token 膨胀。若 kb.settings 配了 rewrite_hint，则领域说明
= description + "\\n" + rewrite_hint（rewrite_hint 用于业务方补充缩写含义等）。

降级：LLM 超时/报错/返回空时，effective_query 回退为 raw_query，标记 degraded，
检索照常继续，绝不抛出。改写耗时单独记录，不算进检索 latency_ms。
"""
from __future__ import annotations

import time

from app.core.config import settings
from app.core.exceptions import LLMProviderError
from app.core.logging import get_logger
from app.providers.llm.base import LLMProvider
from app.providers.query.base import QueryProcessor, QueryProcessResult

logger = get_logger(__name__)

_SYSTEM_PROMPT = """你是检索 query 改写器，不是问答助手。
输入：用户原话 + 知识库名称 + 知识库领域说明。
输出：一条中文短句，更贴近文档常用表述，不超过 30 字。
不编造事实，不扩展用户没问的内容，不生成答案。
只输出改写后的句子，放在 JSON 字段 rewritten_query 中，不输出解释。
返回格式：{"rewritten_query": "..."}"""


class LLMRewriteProcessor(QueryProcessor):
    def __init__(
        self,
        llm_provider: LLMProvider,
        *,
        timeout_ms: int | None = None,
        temperature: float = 0.0,
    ):
        self._llm = llm_provider
        self._timeout_ms = (
            timeout_ms if timeout_ms is not None else settings.query_rewrite_timeout_ms
        )
        self._temperature = temperature

    async def process(
        self,
        result: QueryProcessResult,
        *,
        kb_name: str,
        kb_description: str | None,
        kb_settings: dict,
    ) -> QueryProcessResult:
        # 领域说明 = description + "\n" + rewrite_hint（有 hint 时）
        desc = kb_description or ""
        hint = (kb_settings or {}).get("rewrite_hint")
        if hint:
            desc = f"{desc}\n{hint}" if desc else hint

        payload = {
            "raw_query": result.raw_query,
            "kb_name": kb_name,
            "kb_description": desc,
        }
        started = time.perf_counter()
        try:
            raw = await self._llm.chat_json(
                system_prompt=_SYSTEM_PROMPT,
                user_payload=payload,
                temperature=self._temperature,
                timeout_seconds=max(1, round(self._timeout_ms / 1000)),
            )
            rewritten = ((raw or {}).get("rewritten_query") or "").strip()
            if not rewritten:
                raise LLMProviderError("empty rewritten_query")
            result.effective_query = rewritten
            result.strategy = "rewrite"
        except Exception as exc:  # 任何异常都降级，绝不 500
            result.degraded = True
            result.degraded_reason = str(exc)[:200]
            result.effective_query = result.raw_query
            result.strategy = "rewrite"
            logger.warning("QUERY_REWRITE_DEGRADED | reason=%s", result.degraded_reason)
        finally:
            result.rewrite_latency_ms = int((time.perf_counter() - started) * 1000)
        return result
