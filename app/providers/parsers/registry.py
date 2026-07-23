"""文件扩展名 → DocumentParser 的注册表。

注册顺序：DocxParser → PdfParser → MarkdownParser。
所有不匹配的扩展名最终落入 NoopParser，后者会抛出 PARAM_ERROR。
"""
from __future__ import annotations

from pathlib import Path

from app.providers.parsers.base import DocumentParser
from app.providers.parsers.docx import DocxParser
from app.providers.parsers.markdown import MarkdownParser
from app.providers.parsers.noop import NoopParser
from app.providers.parsers.pdf import PdfParser

_PARSERS: list[DocumentParser] = [DocxParser(), PdfParser(), MarkdownParser()]
_NOOP = NoopParser()


def get_document_parser(filename: str) -> DocumentParser:
    """根据文件名（扩展名）返回对应的 DocumentParser 实例。

    扩展名映射表：
        .docx  → DocxParser  （mammoth → Markdown）
        .pdf   → PdfParser   （PyMuPDF 文本提取）
        .md    → MarkdownParser（source_type="markdown"）
        .txt   → MarkdownParser（source_type="text"）
        其他   → NoopParser  （抛出 PARAM_ERROR）
    """
    ext = Path(filename).suffix.lower()  # noqa: F841  kept for clarity
    for parser in _PARSERS:
        if parser.supports(filename):
            return parser
    return _NOOP
