"""DocumentParser abstraction.

Normalizes an uploaded source into plain text before splitting. Stage 1 only handles
raw text (.txt / .md style). Later parsers (PDF, DOCX, HTML) implement the same
interface without changing the indexing pipeline.
"""
from __future__ import annotations

from abc import ABC, abstractmethod


class DocumentParser(ABC):
    @abstractmethod
    def supports(self, source_type: str) -> bool:
        """Whether this parser can handle the given source_type."""
        raise NotImplementedError

    @abstractmethod
    def parse(self, content: str, *, source_type: str = "text") -> str:
        """Return normalized plain text for downstream splitting."""
        raise NotImplementedError
