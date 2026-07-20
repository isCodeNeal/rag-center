"""Text splitting.

`TextSplitter` is an abstraction so the chunking strategy can evolve (token-based,
recursive, semantic) without touching the indexing service. Stage 1 ships a simple
character-window splitter driven by CHUNK_SIZE / CHUNK_OVERLAP.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from app.core.config import settings


class TextSplitter(ABC):
    @abstractmethod
    def split(self, text: str) -> list[str]:
        """Split raw text into an ordered list of non-empty chunks."""
        raise NotImplementedError


class CharacterTextSplitter(TextSplitter):
    """Fixed-size sliding window over characters with overlap.

    Good enough for the stage-1 closed loop and easy to reason about. Swap for a
    token-aware or recursive splitter later behind the same interface.
    """

    def __init__(self, chunk_size: int | None = None, chunk_overlap: int | None = None):
        self.chunk_size = chunk_size or settings.chunk_size
        self.chunk_overlap = chunk_overlap if chunk_overlap is not None else settings.chunk_overlap
        if self.chunk_size <= 0:
            raise ValueError("chunk_size must be > 0")
        if self.chunk_overlap < 0 or self.chunk_overlap >= self.chunk_size:
            raise ValueError("chunk_overlap must be in [0, chunk_size)")

    def split(self, text: str) -> list[str]:
        text = (text or "").strip()
        if not text:
            return []

        step = self.chunk_size - self.chunk_overlap
        chunks: list[str] = []
        start = 0
        length = len(text)
        while start < length:
            end = start + self.chunk_size
            piece = text[start:end].strip()
            if piece:
                chunks.append(piece)
            if end >= length:
                break
            start += step
        return chunks
