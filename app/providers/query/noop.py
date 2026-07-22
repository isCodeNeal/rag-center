"""直通处理器，不做任何改写或扩展。"""
from __future__ import annotations

from app.providers.query.base import QueryProcessor, QueryProcessResult


class NoopProcessor(QueryProcessor):
    async def process(
        self,
        result: QueryProcessResult,
        *,
        kb_name: str,
        kb_description: str | None,
        kb_settings: dict,
    ) -> QueryProcessResult:
        return result
