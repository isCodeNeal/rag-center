"""Catch-all 解析器：拦截不支持的文件格式并抛出 PARAM_ERROR。"""
from __future__ import annotations

from app.core.error_codes import ErrorCode
from app.core.exceptions import raise_error
from app.providers.parsers.base import DocumentParser, ParsedDocument

_SUPPORTED_FORMATS = ".txt, .md, .docx, .pdf"


class NoopParser(DocumentParser):
    def supports(self, filename: str, mime_type: str | None = None) -> bool:
        return True

    async def parse(self, file_bytes: bytes, *, filename: str) -> ParsedDocument:
        raise_error(
            ErrorCode.PARAM_ERROR,
            msg=f"不支持的文件格式，当前支持：{_SUPPORTED_FORMATS}",
            detail=f"no parser found for {filename}",
        )
