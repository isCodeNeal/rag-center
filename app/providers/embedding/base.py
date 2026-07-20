"""EmbeddingProvider 抽象接口。

业务/service 代码只依赖这个接口，永远不直接依赖具体的模型厂商。可以替换成其它
provider（Azure、本地部署、Cohere 兼容等），而无需改动 indexing 或 retrieval 服务。
"""
from __future__ import annotations

from abc import ABC, abstractmethod


class EmbeddingProvider(ABC):
    @property
    @abstractmethod
    def model(self) -> str:
        """底层使用的 embedding 模型名称。"""
        raise NotImplementedError

    @property
    @abstractmethod
    def dimension(self) -> int:
        """该 provider 产出的向量维度。"""
        raise NotImplementedError

    @abstractmethod
    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """对一批文本（例如文档 chunk）进行 embedding。"""
        raise NotImplementedError

    @abstractmethod
    async def embed_query(self, text: str) -> list[float]:
        """对单条查询字符串进行 embedding。"""
        raise NotImplementedError
