"""DocumentParser 抽象接口（文件字节流版本）。

第二阶段引入：支持从上传文件（.docx / .pdf / .md / .txt）的字节流中解析文本，
返回结构化的 ParsedDocument。

第一阶段的 TextDocumentParser（纯文本 content 字符串）保留在 text.py，
供 IndexingService 的旧流程继续使用（两个接口并行，互不影响）。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class ParsedDocument:
    content: str        # Markdown 风格纯文本
    source_type: str    # text | markdown | docx | pdf
    metadata: dict = field(default_factory=dict)  # page_count, parser_name, warnings 等


class DocumentParser(ABC):
    @abstractmethod
    def supports(self, filename: str, mime_type: str | None = None) -> bool:
        """该 parser 是否支持处理给定文件名（及可选 MIME 类型）。"""
        raise NotImplementedError

    @abstractmethod
    async def parse(self, file_bytes: bytes, *, filename: str) -> ParsedDocument:
        """从原始字节流解析出归一化文本，供下游切分使用。"""
        raise NotImplementedError
