"""文档内容准备 —— 全项目唯一的解析入口。

不在 Route 或 Task 里散落 if/else 文件类型判断。
"""
from __future__ import annotations

import os

from app.core.error_codes import ErrorCode
from app.core.exceptions import raise_error
from app.providers.parsers.base import ParsedDocument
from app.providers.parsers.registry import get_document_parser


async def prepare_document_content(
    *,
    content: str | None,
    file_path: str | None,
    filename: str | None,
) -> ParsedDocument:
    """将「已有文本」或「上传文件路径」统一转换为 ParsedDocument。

    优先级：content（pass-through）> file_path（读字节 → 解析）> 两者皆无（报错）。
    """
    # 已有非空 content（JSON 文本 upload）→ pass-through
    if content:
        return ParsedDocument(
            content=content,
            source_type="text",
            metadata={"parser": "passthrough"},
        )

    # 有 file_path → 读 bytes → 选 Parser → parse
    if file_path:
        with open(file_path, "rb") as f:
            file_bytes = f.read()
        fname = filename or os.path.basename(file_path)
        parser = get_document_parser(fname)
        return await parser.parse(file_bytes, filename=fname)

    # 两者都没有
    raise_error(ErrorCode.DOCUMENT_CONTENT_EMPTY, msg="文档内容为空，请提供文本内容或上传文件")
