"""文本切分。

`TextSplitter` 是一层抽象，使得分块策略可以持续演进（基于 token、递归、语义等），
而不必改动 indexing service。第一阶段提供一个简单的、由 CHUNK_SIZE / CHUNK_OVERLAP
驱动的字符窗口切分器。
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from app.core.config import settings


class TextSplitter(ABC):
    @abstractmethod
    def split(self, text: str) -> list[str]:
        """将原始文本切分为一个有序的非空 chunk 列表。"""
        raise NotImplementedError


class CharacterTextSplitter(TextSplitter):
    """按字符的固定大小滑动窗口切分，窗口之间带重叠。

    对于第一阶段跑通闭环来说已经够用，逻辑也容易理解。后续可以在同一接口背后
    换成 token-aware 或递归式的切分器。
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
