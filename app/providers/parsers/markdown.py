"""Markdown / 纯文本文件解析器（.md → source_type="markdown"，.txt → source_type="text"）。"""
from __future__ import annotations

from pathlib import Path

from app.providers.parsers.base import DocumentParser, ParsedDocument

_EXTENSIONS = {".md", ".txt"}


class MarkdownParser(DocumentParser):
    def supports(self, filename: str, mime_type: str | None = None) -> bool:
        return Path(filename).suffix.lower() in _EXTENSIONS

    async def parse(self, file_bytes: bytes, *, filename: str) -> ParsedDocument:
        ext = Path(filename).suffix.lower()
        content = (
            file_bytes.decode("utf-8", errors="replace")
            .replace("\r\n", "\n")
            .replace("\r", "\n")
            .strip()
        )
        source_type = "markdown" if ext == ".md" else "text"
        return ParsedDocument(
            content=content,
            source_type=source_type,
            metadata={"parser": "markdown", "filename": filename},
        )
