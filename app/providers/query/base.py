"""提问语义优化的数据结构与处理器抽象。

QueryProcessResult 覆盖同一 query 的三个阶段：
    raw_query       用户原话，全程不变
    effective_query LLM 改写后的句子，未改写时等于 raw_query
    search_query    词表扩展后实际送入检索的最终句子，无扩展时等于 effective_query
业务代码始终用 search_query 检索即可。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class QueryProcessResult:
    raw_query: str
    effective_query: str
    search_query: str
    strategy: str = "noop"           # noop 或 rewrite
    rewrite_latency_ms: int = 0      # 改写耗时，单独计，不混入检索 latency_ms
    degraded: bool = False           # LLM 改写是否失败并回退
    degraded_reason: str | None = None
    synonym_applied: bool = False
    synonym_expansions: list[str] = field(default_factory=list)

    @classmethod
    def from_raw(cls, raw_query: str) -> "QueryProcessResult":
        return cls(raw_query=raw_query, effective_query=raw_query, search_query=raw_query)


class QueryProcessor(ABC):
    @abstractmethod
    async def process(
        self,
        result: QueryProcessResult,
        *,
        kb_name: str,
        kb_description: str | None,
        kb_settings: dict,
    ) -> QueryProcessResult:
        """就地推进 result 的某一阶段并返回。处理器之间通过 result 传递状态。"""
        raise NotImplementedError
