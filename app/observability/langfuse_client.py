"""Langfuse 可观测性客户端封装。

LANGFUSE_ENABLED=false 时所有操作静默无操作，调用方无需判空。
Langfuse SDK 内部 httpx 访问时关闭系统代理（trust_env=False），避免 localhost 502。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# 全局单例，避免每次请求重新建连
_langfuse_client = None


def get_langfuse_client():
    """惰性创建全局 Langfuse 客户端。LANGFUSE_ENABLED=false 时返回 None。"""
    global _langfuse_client
    if not settings.langfuse_enabled:
        return None
    if _langfuse_client is None:
        try:
            import httpx
            from langfuse import Langfuse

            # 注入自定义 httpx client，关闭系统代理避免本地 502
            _http_client = httpx.Client(trust_env=False)
            _langfuse_client = Langfuse(
                public_key=settings.langfuse_public_key,
                secret_key=settings.langfuse_secret_key,
                host=settings.langfuse_host,
                httpx_client=_http_client,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("LANGFUSE_CLIENT_INIT_FAILED | error=%s", exc)
            return None
    return _langfuse_client


@dataclass
class _SpanData:
    """暂存一个子 span 的数据，RetrieveObservability 最终一次性写入。"""

    name: str
    input: dict = field(default_factory=dict)
    output: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)


class RetrieveObservability:
    """封装一次 retrieve 调用的 Langfuse trace 生命周期。

    用法：
        obs = RetrieveObservability(trace_name="rag_retrieve", metadata={...})
        obs.record_query_processing(...)
        obs.record_retrieval(...)
        obs.record_rerank(...)
        trace_id = obs.finish(output={...})   # 返回 trace_id，失败时返回 None

    LANGFUSE_ENABLED=false 或写入异常时静默，不影响 retrieve 正常返回。
    """

    def __init__(self, *, metadata: dict[str, Any] | None = None):
        self._lf = get_langfuse_client()
        self._trace = None
        self._spans: list[_SpanData] = []
        self._metadata = metadata or {}

        if self._lf is not None:
            try:
                self._trace = self._lf.trace(
                    name="rag_retrieve",
                    metadata=self._metadata,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("LANGFUSE_TRACE_CREATE_FAILED | error=%s", exc)
                self._trace = None

    def record_query_processing(
        self,
        *,
        raw_query: str,
        effective_query: str,
        search_query: str,
        synonym_applied: bool,
        synonym_expansions: list[str],
        degraded: bool,
    ) -> None:
        self._spans.append(
            _SpanData(
                name="query_processing",
                input={"raw_query": raw_query},
                output={
                    "effective_query": effective_query,
                    "search_query": search_query,
                },
                metadata={
                    "synonym_applied": synonym_applied,
                    "synonym_expansions": synonym_expansions,
                    "rewrite_degraded": degraded,
                },
            )
        )

    def record_retrieval(
        self,
        *,
        mode: str,
        vector_count: int | None,
        bm25_count: int | None,
        fused_count: int | None,
        degraded: bool,
    ) -> None:
        self._spans.append(
            _SpanData(
                name="retrieval",
                input={"mode": mode},
                output={
                    "vector_count": vector_count,
                    "bm25_count": bm25_count,
                    "fused_count": fused_count,
                },
                metadata={"hybrid_degraded": degraded},
            )
        )

    def record_rerank(
        self,
        *,
        enabled: bool,
        candidate_count: int | None,
        degraded: bool,
    ) -> None:
        self._spans.append(
            _SpanData(
                name="rerank",
                input={"enabled": enabled, "candidate_count": candidate_count},
                output={"degraded": degraded},
            )
        )

    def finish(self, *, chunk_summaries: list[dict]) -> str | None:
        """写入所有 span，flush trace，返回 trace_id。失败时返回 None。"""
        if self._trace is None:
            return None
        try:
            for span_data in self._spans:
                span = self._trace.span(
                    name=span_data.name,
                    input=span_data.input,
                    metadata=span_data.metadata,
                )
                span.end(output=span_data.output)

            # trace output 只存 chunk_id + score 摘要，不塞全文
            self._trace.update(
                output={"chunks": chunk_summaries},
            )
            self._lf.flush()
            return self._trace.id
        except Exception as exc:  # noqa: BLE001
            logger.warning("LANGFUSE_TRACE_FINISH_FAILED | error=%s", exc)
            return None
