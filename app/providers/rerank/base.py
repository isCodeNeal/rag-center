"""RerankProvider 抽象接口。

在向量召回之后、返回给业务方之前，对候选 chunk 做相关性重新打分和排序。
`LLMRerankProvider` 基于通用 `LLMProvider` 实现；`NoopRerankProvider` 是不重排的
占位实现，用于配置关闭 rerank 的场景。RagService 只依赖这个接口，不关心具体
实现方式。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class RerankProvider(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        """provider 标识，用于写入 metadata.rerank.provider（例如 "llm"、"noop"）。"""
        raise NotImplementedError

    @abstractmethod
    async def rerank(
        self,
        *,
        query: str,
        chunks: list[dict[str, Any]],
        top_n: int,
    ) -> list[dict[str, Any]]:
        """对候选 chunk 重新打分排序，返回最终保留的 top_n 个。

        - query：用户原始 query。
        - chunks：向量召回后的候选 chunk 列表，每个 dict 至少包含
          document_id、chunk_id、title、content、score（原始向量分数）。
        - top_n：最终返回的 chunk 数量。

        返回的每个 chunk 需要保留输入的原始字段，并新增 `rerank_score` 字段。
        实现内部如果调用大模型失败，应当抛出可识别异常（`RerankError`），由
        调用方（RagService）决定如何降级，而不是在这里静默吞掉错误。
        """
        raise NotImplementedError
