"""DOCX 文档解析器，使用 mammoth 将 .docx 转换为 Markdown 文本。"""
from __future__ import annotations

import io
from pathlib import Path

from app.core.error_codes import ErrorCode
from app.core.exceptions import raise_error
from app.providers.parsers.base import DocumentParser, ParsedDocument


class DocxParser(DocumentParser):
    def supports(self, filename: str, mime_type: str | None = None) -> bool:
        return Path(filename).suffix.lower() == ".docx"

    async def parse(self, file_bytes: bytes, *, filename: str) -> ParsedDocument:
        import mammoth  # type: ignore[import]

        result = mammoth.convert_to_markdown(io.BytesIO(file_bytes))
        content = result.value.strip()
        if not content:
            raise_error(
                ErrorCode.DOCUMENT_PARSE_FAILED,
                detail=f"mammoth returned empty content for {filename}",
            )
        return ParsedDocument(
            content=content,
            source_type="docx",
            metadata={
                "parser": "mammoth",
                "filename": filename,
                "warnings": [str(w) for w in result.messages],
            },
        )
