"""EmbeddingProvider abstraction.

Business/service code depends only on this interface, never on a concrete model
vendor. Swap in other providers (Azure, local, Cohere-compatible) without touching
the indexing or retrieval services.
"""
from __future__ import annotations

from abc import ABC, abstractmethod


class EmbeddingProvider(ABC):
    @property
    @abstractmethod
    def model(self) -> str:
        """Name of the underlying embedding model."""
        raise NotImplementedError

    @property
    @abstractmethod
    def dimension(self) -> int:
        """Vector dimension produced by this provider."""
        raise NotImplementedError

    @abstractmethod
    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts (e.g. document chunks)."""
        raise NotImplementedError

    @abstractmethod
    async def embed_query(self, text: str) -> list[float]:
        """Embed a single query string."""
        raise NotImplementedError
