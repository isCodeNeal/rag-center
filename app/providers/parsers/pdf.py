"""PDF 文档解析器，使用 PyMuPDF (fitz) 提取文本。"""
from __future__ import annotations

from pathlib import Path

from app.core.error_codes import ErrorCode
from app.core.exceptions import raise_error
from app.providers.parsers.base import DocumentParser, ParsedDocument


class PdfParser(DocumentParser):
    def supports(self, filename: str, mime_type: str | None = None) -> bool:
        return Path(filename).suffix.lower() == ".pdf"

    async def parse(self, file_bytes: bytes, *, filename: str) -> ParsedDocument:
        import fitz  # type: ignore[import]  # PyMuPDF

        doc = fitz.open(stream=file_bytes, filetype="pdf")
        pages: list[str] = []
        for i, page in enumerate(doc, start=1):
            text = page.get_text().strip()
            if text:
                pages.append(f"## 第 {i} 页\n\n{text}")

        if not pages:
            raise_error(
                ErrorCode.DOCUMENT_PARSE_FAILED,
                msg="PDF 无可提取文本，可能为扫描件",
                detail=f"fitz found no text in {filename}",
            )
        return ParsedDocument(
            content="\n\n".join(pages),
            source_type="pdf",
            metadata={
                "parser": "pymupdf",
                "filename": filename,
                "page_count": len(doc),
            },
        )
