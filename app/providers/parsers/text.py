"""Plain-text document parser for stage 1 (.txt / .md / raw text)."""
from __future__ import annotations

from app.core.exceptions import UnsupportedSourceType
from app.providers.parsers.base import DocumentParser

_SUPPORTED = {"text", "txt", "md", "markdown", "plain"}


class TextDocumentParser(DocumentParser):
    def supports(self, source_type: str) -> bool:
        return (source_type or "text").lower() in _SUPPORTED

    def parse(self, content: str, *, source_type: str = "text") -> str:
        if not self.supports(source_type):
            raise UnsupportedSourceType(f"unsupported source_type: {source_type}")
        # Normalize newlines; content is already plain text in stage 1.
        return (content or "").replace("\r\n", "\n").replace("\r", "\n").strip()
