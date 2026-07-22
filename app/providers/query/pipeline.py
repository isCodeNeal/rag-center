"""串联提问语义优化两层：LLM 改写（可选）→ 词表扩展（有 settings 即尝试）。

按 rewrite_enabled 决定是否改写（请求级优先于全局，由调用方在传入前解析好）。
词表扩展始终执行，不受 rewrite_enabled 控制——即使不开改写，词表也会生效。
"""
from __future__ import annotations

from app.providers.llm.base import LLMProvider
from app.providers.query.base import QueryProcessResult
from app.providers.query.llm_rewrite import LLMRewriteProcessor
from app.providers.query.synonym_expander import SynonymExpander


class QueryPipeline:
    def __init__(self, llm_provider: LLMProvider):
        self._llm = llm_provider
        self._synonym = SynonymExpander()

    async def run(
        self,
        raw_query: str,
        *,
        rewrite_enabled: bool,
        kb_name: str,
        kb_description: str | None,
        kb_settings: dict,
    ) -> QueryProcessResult:
        result = QueryProcessResult.from_raw(raw_query)
        ctx = dict(kb_name=kb_name, kb_description=kb_description, kb_settings=kb_settings)
        if rewrite_enabled:
            result = await LLMRewriteProcessor(self._llm).process(result, **ctx)
        # 词表扩展始终尝试（无 synonyms 时是直通）
        result = await self._synonym.process(result, **ctx)
        return result
